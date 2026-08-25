// W10 验收测试（卡 #27）：本地图像编解码——尺寸解析、占位 PNG、MP4 判定。
// 测试先行（g050）：实现缺失时 import 折叠为哨兵，红因=断言失败。
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

type ImageDims = { width: number; height: number; kind: string };
type ImagecodecModule = {
  img?: {
    parseImageSize?: (buf: Buffer) => ImageDims | null;
    fileImageSize?: (f: string) => ImageDims | null;
    solidPng?: (w: number, h: number, rgb?: [number, number, number]) => Buffer;
    placeholderPng?: (role: string) => Buffer;
    writePlaceholderPng?: (
      role: string,
      f: string,
    ) => { width: number; height: number; bytes: number; mode: string };
    looksLikeMp4?: (buf: Buffer) => boolean;
  };
};

const load = async (): Promise<ImagecodecModule> =>
  (await import("../../../src/lib/img.js").catch(
    () => ({}),
  )) as ImagecodecModule;

const ic = await load();
const FIXTURES = path.resolve(import.meta.dirname, "../../../tools/fixtures");
const TMP = path.resolve(import.meta.dirname, "../../../../.tmp");

function readAsset(relPath: string): Buffer {
  try {
    return fs.readFileSync(path.resolve(import.meta.dirname, relPath));
  } catch {
    return Buffer.alloc(0);
  }
}

fs.mkdirSync(TMP, { recursive: true });

describe("W10 imagecodec：尺寸解析与占位 PNG（A2 规格面）", () => {
  it("solidPng 生成合法 PNG 且尺寸可解析", () => {
    const buf = ic.img?.solidPng?.(64, 48, [1, 2, 3]) ?? Buffer.alloc(0);
    expect(buf.slice(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    expect(ic.img?.parseImageSize?.(buf)).toEqual({
      width: 64,
      height: 48,
      kind: "png",
    });
  });
  it("真实 JPEG/PNG fixture 尺寸解析", () => {
    expect(
      ic.img?.fileImageSize?.(path.join(FIXTURES, "fixture_photo.jpg")),
    ).toEqual({ width: 600, height: 400, kind: "jpeg" });
    expect(
      ic.img?.fileImageSize?.(path.join(FIXTURES, "fixture_tiny.png")),
    ).toEqual({ width: 32, height: 32, kind: "png" });
  });
  it("占位图：主图 1024²（≥800 官方下限）、详情 900²（>260）", () => {
    const main = ic.img?.placeholderPng?.("main_image") ?? Buffer.alloc(0);
    const det = ic.img?.placeholderPng?.("detail_image") ?? Buffer.alloc(0);
    expect(ic.img?.parseImageSize?.(main)).toEqual({
      width: 1024,
      height: 1024,
      kind: "png",
    });
    expect(ic.img?.parseImageSize?.(det)).toEqual({
      width: 900,
      height: 900,
      kind: "png",
    });
  });
  it("writePlaceholderPng 落盘并返回尺寸字节（主图/详情两种角色）", () => {
    const dir = fs.mkdtempSync(path.join(TMP, "ph-"));
    const main = ic.img?.writePlaceholderPng?.(
      "main_image",
      path.join(dir, "main.png"),
    );
    const det = ic.img?.writePlaceholderPng?.(
      "detail_image",
      path.join(dir, "det.png"),
    );
    expect(main).toMatchObject({ width: 1024, mode: "local-placeholder" });
    expect(det).toMatchObject({ width: 900, mode: "local-placeholder" });
    expect((main?.bytes ?? 0) > 1000).toBe(true);
    expect(fs.existsSync(path.join(dir, "main.png"))).toBe(true);
  });
  it("无法识别的输入 → null（不抛异常）", () => {
    expect(ic.img?.parseImageSize?.(Buffer.from("notanimage"))).toBeNull();
    expect(
      ic.img?.fileImageSize?.(path.join(TMP, "definitely-missing.png")),
    ).toBeNull();
  });
  it("looksLikeMp4：预置占位 mp4 通过；PNG/碎片不通过", () => {
    const mp4 = readAsset("../../../src/assets/placeholder_video.mp4");
    expect(ic.img?.looksLikeMp4?.(mp4)).toBe(true);
    expect(
      ic.img?.looksLikeMp4?.(ic.img?.solidPng?.(10, 10) ?? Buffer.alloc(0)),
    ).toBe(false);
    expect(ic.img?.looksLikeMp4?.(Buffer.from("x"))).toBe(false);
  });
});
