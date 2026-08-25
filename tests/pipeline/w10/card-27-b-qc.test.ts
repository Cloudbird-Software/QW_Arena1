// W10 验收测试（卡 #27，图像链路）：产物规格 QC 纯函数——
// inspectImage 三规则（主图 ≥800 / 详情与场景 >260 / ≤5MB）、inspectText <1MB、
// inspectVideo box+尺寸、normalizeImage 动作计划、阈值资产与官方 A2 一致。
import { describe, expect, it } from "vitest";

type QcModule = {
  inspectImage?: (a: {
    role: string;
    width: number;
    height: number;
    bytes: number;
  }) => Array<{ rule: string; message: string }>;
  inspectText?: (bytes: number) => Array<{ rule: string }>;
  inspectVideo?: (a: {
    bytes: number;
    hasBoxSignature: boolean;
  }) => Array<{ rule: string }>;
  normalizeImage?: (a: {
    role: string;
    width: number;
    height: number;
    bytes: number;
  }) => { artifactRole: string; actions: string[] };
  listSpecThresholds?: () => Array<{
    key: string;
    value: number;
    unit: string;
  }>;
};

const load = async (): Promise<QcModule> =>
  (await import("../../../src/lib/qc.js").catch(() => ({}))) as QcModule;

const qc = await load();

describe("W10 qc：规格校验与降级计划（A2 口径）", () => {
  it("inspectImage：主图 <800 违规 / 非方形违规 / 详情 200 违规 / 超 5MB 违规", () => {
    const violations =
      qc.inspectImage?.({
        role: "main_image",
        width: 799,
        height: 800,
        bytes: 100,
      }) ?? [];
    expect(violations.some((v) => v.rule === "min-side")).toBe(true);
    expect(
      qc
        .inspectImage?.({
          role: "main_image",
          width: 1024,
          height: 800,
          bytes: 100,
        })
        ?.map((v) => v.rule),
    ).toEqual(["main-square"]);
    expect(
      qc
        .inspectImage?.({
          role: "detail_image",
          width: 200,
          height: 200,
          bytes: 100,
        })
        ?.map((v) => v.rule),
    ).toEqual(["min-side"]);
    expect(
      qc.inspectImage?.({
        role: "scene_image",
        width: 32,
        height: 32,
        bytes: 100,
      })?.length ?? 0,
    ).toBeGreaterThan(0);
    expect(
      qc
        .inspectImage?.({
          role: "detail_image",
          width: 500,
          height: 500,
          bytes: 6_000_000,
        })
        ?.map((v) => v.rule),
    ).toEqual(["size-budget"]);
    expect(
      qc.inspectImage?.({
        role: "detail_image",
        width: 900,
        height: 900,
        bytes: 100,
      }),
    ).toEqual([]);
  });

  it("inspectText <1MB / inspectVideo box+size 规则", () => {
    expect(qc.inspectText?.(500_000)).toEqual([]);
    expect((qc.inspectText?.(2_000_000) ?? []).length).toBeGreaterThan(0);
    expect(qc.inspectVideo?.({ bytes: 1000, hasBoxSignature: true })).toEqual(
      [],
    );
    expect(
      qc
        .inspectVideo?.({ bytes: 1000, hasBoxSignature: false })
        ?.some((v) => v.rule === "video-box-signature"),
    ).toBe(true);
    expect(
      qc
        .inspectVideo?.({ bytes: 300 * 1024 * 1024, hasBoxSignature: true })
        ?.some((v) => v.rule === "video-too-large"),
    ).toBe(true);
  });

  it("normalizeImage 计划映射：违规→本地动作清单（inspection 接线）", () => {
    const p1 = qc.normalizeImage?.({
      role: "main_image",
      width: 600,
      height: 600,
      bytes: 100,
    });
    expect((p1?.actions ?? []).length).toBeGreaterThanOrEqual(1);
    const p2 = qc.normalizeImage?.({
      role: "detail_image",
      width: 900,
      height: 900,
      bytes: 100,
    });
    expect(p2?.actions).toEqual([]);
  });

  it("规格阈值资产与官方 A2 一致（≥800 / >260 / ≤5MB / 文本<1MB / 视频<200MB）", () => {
    const t = Object.fromEntries(
      (qc.listSpecThresholds?.() ?? []).map((x) => [x.key, x.value]),
    );
    expect(t.main_min_side).toBe(800);
    expect(t.detail_min_side).toBe(260);
    expect(t.max_image_bytes).toBe(5_000_000);
    expect(t.max_text_bytes).toBe(1_000_000);
    expect(t.max_video_bytes).toBe(200 * 1024 * 1024);
  });
});
