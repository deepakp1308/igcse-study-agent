import { describe, expect, it } from "vitest";

import type { RequiredConcept } from "../../types";
import { conceptsToMarks, scoreConcepts } from "./concepts";

const concepts: RequiredConcept[] = [
  { concept: "uses formula n = m / M", marks: 1, hints: ["n = m/M", "n=m/M", "moles equals"] },
  { concept: "correct molar mass of calcium (40 g/mol)", marks: 1, hints: ["40", "Ca = 40"] },
  { concept: "reports units as mol", marks: 1, hints: ["mol"] },
];

describe("scoreConcepts", () => {
  it("hits hints", async () => {
    const r = await scoreConcepts("n = m/M using Ca = 40, answer = 0.25 mol", concepts);
    expect(r.every((x) => x.hit)).toBe(true);
    expect(conceptsToMarks(r).awarded).toBe(3);
  });

  it("partial hits", async () => {
    const r = await scoreConcepts("I wrote 0.25 mol", concepts);
    const { awarded, max } = conceptsToMarks(r);
    expect(awarded).toBeGreaterThan(0);
    expect(awarded).toBeLessThan(max);
    expect(r.find((x) => x.concept === concepts[2].concept)?.hit).toBe(true);
  });

  it("no hits when answer is irrelevant", async () => {
    const r = await scoreConcepts("The sky is blue.", concepts);
    expect(conceptsToMarks(r).awarded).toBe(0);
  });

  it("uses embeddings as a fallback when provided", async () => {
    const fake = async (queries: string[]) => queries.map(() => 0.9);
    const r = await scoreConcepts("unrelated words", concepts, fake);
    expect(r.every((x) => x.hit)).toBe(true);
  });
});
