// W10 验收测试（卡 #27，图像链路基础设施）：本地图像编解码——
// PNG/JPEG/WEBP 尺寸解析、solidPng 合法性与确定占位规格、looksLikeMp4 判定。
// 测试先行（g050）：实现缺失时 import 折叠为哨兵，红因=断言失败。
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

type ImagecodecModule = {
  parseImageSize?: (
    buf: Buffer,
  ) => { width: number; height: number; kind: string } | null;
  fileImageSize?: (
    f: string,
  ) => { width: number; height: number; kind: string } | null;
  solidPng?: (w: number, h: number, rgb?: [number, number, number]) => Buffer;
  placeholderPng?: (role: string) => Buffer;
  writePlaceholderPng?: (
    role: string,
    f: string,
  ) => { width: number; height: number; bytes: number; mode: string };
  looksLikeMp4?: (buf: Buffer) => boolean;
};

const load = async (): Promise<ImagecodecModule> =>
  (await import("../../../src/lib/imagecodec.js").catch(
    () => ({}),
  )) as ImagecodecModule;

const ic = await load();
const FIXTURES = path.resolve(import.meta.dirname, "../../../tools/fixtures");
const TMP = path.resolve(import.meta.dirname, "../../../../.tmp");
fs.mkdirSync(TMP, { recursive: true });

describe("W10 imagecodec：尺寸解析与占位 PNG（A2 规格面）", () => {
  it("solidPng 生成合法 PNG 且尺寸可解析", () => {
    const buf = ic.solidPng?.(64, 48, [1, 2, 3]) ?? Buffer.alloc(0);
    expect(buf.slice(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    const dim = ic.parseImageSize?.(buf);
    expect(dim).toEqual({ width: 64, height: 48, kind: "png" });
  });

  it("真实 JPEG/PNG fixture 尺寸解析", () => {
    expect(
      ic.fileImageSize?.(path.join(FIXTURES, "fixture_photo.jpg")),
    ).toEqual({ width: 600, height: 400, kind: "jpeg" });
    expect(ic.fileImageSize?.(path.join(FIXTURES, "fixture_tiny.png"))).toEqual(
      { width: 32, height: 32, kind: "png" },
    );
  });

  it("占位图：主图 1024²（≥800 官方下限）、详情 900²（>260）", () => {
    const main = ic.placeholderPng?.("main_image") ?? Buffer.alloc(0);
    expect(ic.parseImageSize?.(main)).toEqual({
      width: 1024,
      height: 1024,
      kind: "png",
    });
    const det = ic.placeholderPng?.("detail_image") ?? Buffer.alloc(0);
    expect(ic.parseImageSize?.(det)).toEqual({
      width: 900,
      height: 900,
      kind: "png",
    });
  });

  it("writePlaceholderPng 落盘并返回尺寸字节", () => {
    const dir = fs.mkdtempSync(path.join(TMP, "ph-"));
    const r = ic.writePlaceholderPng?.("main_image", path.join(dir, "x.png"));
    expect(r).toMatchObject({ width: 1024, mode: "local-placeholder" });
    expect((r?.bytes ?? 0) > 1000).toBe(true);
  });

  it("无法识别的输入 → null（不抛异常）", () => {
    expect(ic.parseImageSize?.(Buffer.from("notanimage"))).toBeNull();
    expect(
      ic.fileImageSize?.(path.join(TMP, "definitely-missing.png")),
    ).toBeNull();
  });

  it("looksLikeMp4：预置占位 mp4 通过；PNG/碎片不通过", () => {
    const mp4 = fs.readFileSync(
      path.resolve(
        import.meta.dirname,
        "../../../src/assets/placeholder_video.mp4",
      ),
    );
    expect(ic.looksLikeMp4?.(mp4)).toBe(true);
    expect(ic.looksLikeMp4?.(ic.solidPng?.(10, 10) ?? Buffer.alloc(0))).toBe(
      false,
    );
    expect(ic.looksLikeMp4?.(Buffer.from("x"))).toBe(false);
  });
});
