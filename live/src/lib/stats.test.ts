import { describe, expect, test } from "vitest";
import { accuracy, bootstrapCI, formatPct } from "./stats";

const twelveOfEighteen = [...Array(12).fill(1), ...Array(6).fill(0)];

describe("accuracy", () => {
  test("empty input is null, not NaN", () => {
    expect(accuracy([])).toBeNull();
  });
  test("12 of 18 is 0.6667", () => {
    expect(accuracy(twelveOfEighteen)).toBeCloseTo(0.6667, 4);
  });
});

describe("bootstrapCI", () => {
  test("empty input is null", () => {
    expect(bootstrapCI([])).toBeNull();
  });
  test("all-correct interval is [1, 1]", () => {
    expect(bootstrapCI(Array(18).fill(1))).toEqual([1, 1]);
  });
  test("brackets the mean", () => {
    const [lo, hi] = bootstrapCI(twelveOfEighteen)!;
    expect(lo).toBeLessThan(0.6667);
    expect(hi).toBeGreaterThan(0.6667);
    expect(lo).toBeGreaterThanOrEqual(0);
    expect(hi).toBeLessThanOrEqual(1);
  });
  test("same input gives the same interval", () => {
    expect(bootstrapCI(twelveOfEighteen)).toEqual(bootstrapCI(twelveOfEighteen));
  });
});

describe("formatPct", () => {
  test("null renders as a dash, never 0% or NaN", () => {
    expect(formatPct(null)).toBe("—");
    expect(formatPct(accuracy([]))).toBe("—");
  });
  test("one decimal place", () => {
    expect(formatPct(0.9444)).toBe("94.4%");
    expect(formatPct(1)).toBe("100.0%");
  });
});
