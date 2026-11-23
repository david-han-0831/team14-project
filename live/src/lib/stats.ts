// 정답률과 문항 단위 부트스트랩 신뢰구간.
// evolve/solve.py 의 bootstrap_ci 와 같은 방식(재표집 2000회, 2.5·97.5 백분위)이지만
// 난수 생성기가 달라 파이썬 결과와 소수 셋째 자리에서 다를 수 있다.

export function accuracy(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function bootstrapCI(values: number[], nBoot = 2000, seed = 14): [number, number] | null {
  const n = values.length;
  if (n === 0) return null;
  const rnd = mulberry32(seed);
  const means = new Array<number>(nBoot);
  for (let b = 0; b < nBoot; b++) {
    let s = 0;
    for (let i = 0; i < n; i++) s += values[Math.floor(rnd() * n)];
    means[b] = s / n;
  }
  means.sort((x, y) => x - y);
  return [means[Math.floor(0.025 * nBoot)], means[Math.floor(0.975 * nBoot)]];
}

export function formatPct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}
