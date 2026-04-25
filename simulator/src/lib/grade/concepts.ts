import type { ConceptResult, RequiredConcept } from "../../types";

/**
 * Concept-coverage scoring for free-text answers.
 *
 * The grader runs two cheap, local signals in sequence:
 *
 *   1. Keyword/phrase match against the concept's `hints`. Any hit = concept hit.
 *   2. TF-IDF-ish token overlap between the concept string itself and the student
 *      answer. Threshold tuned for short IGCSE answers.
 *
 * Optional progressive enhancement: the `embeddingsFn` callback lets you supply
 * a similarity function (e.g. backed by `@xenova/transformers`) that runs in
 * the browser if available; it is used as a tiebreaker for concepts that did
 * not hit on tokens.
 */

export type EmbeddingsFn = (queries: string[], target: string) => Promise<number[]>;

function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9+.=\-/\s]/g, " ").replace(/\s+/g, " ").trim();
}

function tokenize(s: string): string[] {
  return normalize(s).split(" ").filter((t) => t.length > 1);
}

function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 && b.size === 0) return 0;
  let inter = 0;
  a.forEach((t) => {
    if (b.has(t)) inter += 1;
  });
  const union = a.size + b.size - inter;
  return union === 0 ? 0 : inter / union;
}

const JACCARD_HIT = 0.2;
const EMBED_HIT = 0.55;

export async function scoreConcepts(
  studentAnswer: string,
  concepts: RequiredConcept[],
  embeddingsFn?: EmbeddingsFn,
): Promise<ConceptResult[]> {
  const answer = normalize(studentAnswer);
  const answerTokens = new Set(tokenize(answer));

  // Pass 1: hints + jaccard
  const results: ConceptResult[] = concepts.map((c) => {
    const hintHit = c.hints.some((h) => {
      const hn = normalize(h);
      if (!hn) return false;
      return answer.includes(hn);
    });
    if (hintHit) {
      return { concept: c.concept, marks: c.marks, awarded: c.marks, hit: true };
    }
    const conceptTokens = new Set(tokenize(c.concept + " " + c.hints.join(" ")));
    const sim = jaccard(conceptTokens, answerTokens);
    if (sim >= JACCARD_HIT) {
      return { concept: c.concept, marks: c.marks, awarded: c.marks, hit: true };
    }
    return { concept: c.concept, marks: c.marks, awarded: 0, hit: false };
  });

  if (!embeddingsFn) return results;

  // Pass 2: embeddings for concepts that didn't hit
  const missIndices = results.map((r, i) => (r.hit ? -1 : i)).filter((i) => i >= 0);
  if (missIndices.length === 0) return results;
  const queries = missIndices.map((i) => concepts[i].concept);
  let sims: number[] = [];
  try {
    sims = await embeddingsFn(queries, answer);
  } catch {
    sims = queries.map(() => 0);
  }
  missIndices.forEach((idx, k) => {
    if ((sims[k] ?? 0) >= EMBED_HIT) {
      results[idx].awarded = results[idx].marks;
      results[idx].hit = true;
    }
  });
  return results;
}

export function conceptsToMarks(results: ConceptResult[]): {
  awarded: number;
  max: number;
} {
  const awarded = results.reduce((s, r) => s + r.awarded, 0);
  const max = results.reduce((s, r) => s + r.marks, 0);
  return { awarded, max };
}
