import { describe, expect, test } from "vitest";
import { canRun } from "./ui";

describe("canRun", () => {
  const base = { phase: "ready" as const, setName: "week09" as const, loadedSet: "week09" as const, questionCount: 18 };
  test("ready with the selected set loaded", () => expect(canRun(base)).toBe(true));
  test("finished run can be re-run", () => expect(canRun({ ...base, phase: "finished" })).toBe(true));
  test("not while running", () => expect(canRun({ ...base, phase: "running" })).toBe(false));
  test("not while the newly selected set is still loading (old questions on screen)", () =>
    expect(canRun({ ...base, setName: "seed", loadedSet: "week09" })).toBe(false));
  test("not before any bank is loaded", () => expect(canRun({ ...base, loadedSet: null, questionCount: 0 })).toBe(false));
  test("not with an empty bank", () => expect(canRun({ ...base, questionCount: 0 })).toBe(false));
});
