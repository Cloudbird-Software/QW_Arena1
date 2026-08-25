// 并发工具：有界并行（图像/文案管线通用）。
const sleep = (ms: number): Promise<unknown> => {
  return new Promise((r) => setTimeout(r, ms));
};

interface SettledResult<T> {
  status: "fulfilled" | "rejected";
  value?: T;
  reason?: unknown;
}

/**
 * 有界并发映射：同时最多 n 个任务。
 * 任一项失败 → 该项记入 results（与 Promise.allSettled 语义一致），不整体中断。
 * 顺序与输入一致。
 */
export async function mapLimit<T, R>(
  items: T[],
  n: number,
  fn: (item: T, idx: number) => Promise<R>,
): Promise<SettledResult<R>[]> {
  const results = new Array<SettledResult<R>>(items.length);
  let next = 0;
  const workers = Array.from(
    { length: Math.min(n, items.length) },
    async () => {
      while (next < items.length) {
        const idx = next;
        next += 1;
        try {
          results[idx] = {
            status: "fulfilled",
            value: await fn(items[idx]!, idx),
          };
        } catch (e) {
          results[idx] = { status: "rejected", reason: e };
        }
      }
    },
  );
  await Promise.all(workers);
  return results;
}

/** 带死线检查的等待器：剩余时间不足 ms 则抛错（调用方快速降级）。 */
export async function waitWithBudget(
  ms: number,
  remainingMs: () => number,
  what: string,
): Promise<void> {
  if (remainingMs() < ms + 15000) {
    throw new Error(`budget exhausted before ${what}`);
  }
  await sleep(ms);
}

export { sleep };
