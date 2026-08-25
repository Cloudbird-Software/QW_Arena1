// 本地图像编解码：PNG/JPEG 尺寸解析（QC 用）+ 纯 zlib 占位 PNG 生成。
// 零依赖、确定性：所有失败返回 null，绝不抛异常。
import zlib from "node:zlib";
import fs from "node:fs";

interface ImageSize {
  width: number;
  height: number;
  kind: string;
}

/** PNG: 8-byte sig + IHDR(13) w/h big-endian。 */
function pngSize(buf: Buffer): ImageSize | null {
  if (buf.length < 24) return null;
  return {
    width: buf.readUInt32BE(16),
    height: buf.readUInt32BE(20),
    kind: "png",
  };
}

/** JPEG SOF0/1/2/3 标记判定（含符号分量标记排除）。 */
function isSofMarker(marker: number): boolean {
  return (
    marker >= 0xc0 &&
    marker <= 0xcf &&
    marker !== 0xc4 &&
    marker !== 0xc8 &&
    marker !== 0xcc
  );
}

/** JPEG: FF D8 ... SOF0/1/2/3 markers。 */
function jpegSize(buf: Buffer): ImageSize | null {
  let i = 2;
  while (i + 9 < buf.length) {
    if (buf[i] !== 0xff) {
      i += 1;
      continue;
    }
    const marker = buf[i + 1]!;
    if (marker === 0xd8 || marker === 0xd9) {
      i += 2;
      continue;
    }
    if (marker === 0xda) break; // SOS — no more SOF
    const len = buf.readUInt16BE(i + 2);
    if (isSofMarker(marker)) {
      if (i + 9 > buf.length) return null;
      return {
        width: buf.readUInt16BE(i + 7),
        height: buf.readUInt16BE(i + 5),
        kind: "jpeg",
      };
    }
    i += 2 + len;
  }
  return null;
}

/** WEBP: RIFF....WEBP。 */
function webpSize(buf: Buffer): ImageSize | null {
  const fmt = buf.slice(12, 16).toString("ascii");
  if (fmt === "VP8 " && buf.length >= 30) {
    return {
      width: buf.readUInt16LE(26) & 0x3fff,
      height: buf.readUInt16LE(28) & 0x3fff,
      kind: "webp",
    };
  }
  if (fmt === "VP8L" && buf.length >= 25) {
    const b = buf.readUInt32LE(21);
    return {
      width: (b & 0x3fff) + 1,
      height: ((b >> 14) & 0x3fff) + 1,
      kind: "webp",
    };
  }
  return null;
}

/** GIF 头尺寸（89a/87a）。 */
function gifSize(buf: Buffer): ImageSize | null {
  return {
    width: buf.readUInt16LE(6),
    height: buf.readUInt16LE(8),
    kind: "gif",
  };
}

/** 解析图像尺寸（PNG/JPEG/WEBP/GIF 基础支持）；无法识别返回 null。 */
export function parseImageSize(buf: Buffer): ImageSize | null {
  if (!buf || buf.length < 16) return null;
  if (
    buf[0] === 0x89 &&
    buf[1] === 0x50 &&
    buf[2] === 0x4e &&
    buf[3] === 0x47
  ) {
    return pngSize(buf);
  }
  if (buf[0] === 0xff && buf[1] === 0xd8) {
    return jpegSize(buf);
  }
  if (
    buf.slice(0, 4).toString("ascii") === "RIFF" &&
    buf.slice(8, 12).toString("ascii") === "WEBP"
  ) {
    return webpSize(buf);
  }
  if (
    buf.slice(0, 6).toString("ascii") === "GIF89a" ||
    buf.slice(0, 6).toString("ascii") === "GIF87a"
  ) {
    return gifSize(buf);
  }
  return null;
}

/** 文件维度解析（读前 64KB 足够）。 */
export function fileImageSize(filePath: string): ImageSize | null {
  try {
    const fd = fs.openSync(filePath, "r");
    const buf = Buffer.alloc(64 * 1024);
    const n = fs.readSync(fd, buf, 0, buf.length, 0);
    fs.closeSync(fd);
    return parseImageSize(buf.subarray(0, n));
  } catch {
    return null;
  }
}

// ---- 纯色 PNG 生成（v1 代码原样保留：标准 zlib PNG 编码） ----

function buildCrcTable(): Int32Array {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
}

const CRC_TABLE = buildCrcTable();

function crc32(buf: Buffer): number {
  let c = -1;
  for (let i = 0; i < buf.length; i++)
    c = CRC_TABLE[(c ^ buf[i]!) & 0xff]! ^ (c >>> 8);
  return (c ^ -1) >>> 0;
}

function pngChunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

/**
 * 纯色 PNG。占位图 ≥ 规格下限：主图 1024×1024、详情 900×900
 * （官方下限：主图 ≥800×800、详情 >260，额外余量兜 QC）。
 */
export function solidPng(
  w: number,
  h: number,
  [r, g, b]: [number, number, number] = [235, 238, 242],
): Buffer {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // color type RGB
  const row = Buffer.alloc(1 + w * 3);
  for (let x = 0; x < w; x++) {
    row[1 + x * 3] = r;
    row[2 + x * 3] = g;
    row[3 + x * 3] = b;
  }
  const raw = Buffer.concat(Array(h).fill(row) as Buffer[]);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", zlib.deflateSync(raw, { level: 6 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

/** 按角色渲染占位图（主图浅灰、详情浅蓝灰，尺寸达标）。 */
export function placeholderPng(role: string): Buffer {
  if (role === "main_image") return solidPng(1024, 1024, [235, 238, 242]);
  return solidPng(900, 900, [225, 232, 238]);
}

/** 写入占位图文件并返回 {width, height, bytes, mode}。 */
export function writePlaceholderPng(
  role: string,
  filePath: string,
): { width: number; height: number; bytes: number; mode: string } {
  const buf =
    role === "main_image"
      ? solidPng(1024, 1024, [235, 238, 242])
      : solidPng(900, 900, [225, 232, 238]);
  fs.writeFileSync(filePath, buf);
  return {
    width: role === "main_image" ? 1024 : 900,
    height: role === "main_image" ? 1024 : 900,
    bytes: buf.length,
    mode: "local-placeholder",
  };
}

/** 文件是否为合法 MP4/MOV（ftyp 盒前置）。 */
export function looksLikeMp4(buf: Buffer): boolean {
  if (!buf || buf.length < 32) return false;
  const box = buf.slice(4, 8).toString("ascii");
  if (box !== "ftyp" && box !== "moov" && box !== "mdat" && box !== "wide")
    return false;
  const major = buf.slice(8, 12).toString("ascii");
  return (
    /^(isom|mp42|avc1|M4V |qt {2})/.test(major) ||
    buf.includes(Buffer.from("moov"))
  );
}
