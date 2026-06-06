import { describe, it, expect } from "vitest";
import { scoreToVerdict } from "./types";

/**
 * Smoke tests for scoreToVerdict.
 * Purpose: verify the test framework is wired correctly AND lock down
 * the boundary values of the scoring function so regressions are caught.
 */
describe("scoreToVerdict", () => {
  it("returns safe for scores >= 70", () => {
    expect(scoreToVerdict(100)).toBe("safe");
    expect(scoreToVerdict(70)).toBe("safe");
  });

  it("returns caution for scores 40–69", () => {
    expect(scoreToVerdict(69)).toBe("caution");
    expect(scoreToVerdict(40)).toBe("caution");
  });

  it("returns danger for scores < 40", () => {
    expect(scoreToVerdict(39)).toBe("danger");
    expect(scoreToVerdict(0)).toBe("danger");
  });
});
