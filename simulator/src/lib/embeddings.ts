/**
 * Optional: browser MiniLM embeddings via @xenova/transformers.
 *
 * Loaded on demand (dynamic import) so the initial bundle stays small and
 * the concept grader continues to work if the WASM model fails to load.
 */

import type { EmbeddingsFn } from "./grade/concepts";

type Pipeline = (input: string | string[], opts?: Record<string, unknown>) => Promise<{
  data: Float32Array;
  dims: number[];
}>;

let extractorPromise: Promise<Pipeline> | null = null;

function getExtractor(): Promise<Pipeline> {
  if (extractorPromise) return extractorPromise;
  extractorPromise = (async () => {
    const { pipeline, env } = await import("@xenova/transformers");
    env.allowLocalModels = false;
    env.useBrowserCache = true;
    return pipeline(
      "feature-extraction",
      "Xenova/all-MiniLM-L6-v2",
    ) as unknown as Pipeline;
  })();
  return extractorPromise;
}

function cosineFromFlat(flat: Float32Array, dim: number, i: number, j: number): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  const aStart = i * dim;
  const bStart = j * dim;
  for (let k = 0; k < dim; k++) {
    const a = flat[aStart + k];
    const b = flat[bStart + k];
    dot += a * b;
    na += a * a;
    nb += b * b;
  }
  if (na === 0 || nb === 0) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

export const browserEmbeddings: EmbeddingsFn = async (queries, target) => {
  try {
    const extractor = await getExtractor();
    const all = [...queries, target];
    const { data, dims } = await extractor(all, { pooling: "mean", normalize: true });
    const dim = dims[dims.length - 1];
    const targetIdx = queries.length;
    return queries.map((_, i) => cosineFromFlat(data, dim, i, targetIdx));
  } catch (e) {
    console.warn("[embeddings] unavailable, falling back", e);
    return queries.map(() => 0);
  }
};

export function embeddingsAvailable(): boolean {
  return typeof WebAssembly !== "undefined" && typeof window !== "undefined";
}
