import { describe, expect, it } from "vitest";
import { compactUrl, scoreColor } from "./utils";

describe("utils", () => {
  it("assigns score colors by threshold", () => {
    expect(scoreColor(95)).toBe("#2fb391");
    expect(scoreColor(75)).toBe("#d49b3d");
    expect(scoreColor(10)).toBe("#cc4f69");
  });

  it("compacts long urls", () => {
    const url = "https://example.com/path/to/a/very/long/path/that-needs-compaction";
    expect(compactUrl(url, 20).length).toBe(20);
  });
});
