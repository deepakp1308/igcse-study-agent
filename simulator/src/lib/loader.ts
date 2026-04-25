import type { SetsIndex, SimulatorSet } from "../types";

const basePath = (import.meta.env.BASE_URL ?? "/").replace(/\/$/, "");

export function setsUrl(file: string): string {
  return `${basePath}/sets/${file}`;
}

export async function loadIndex(): Promise<SetsIndex> {
  const res = await fetch(`${basePath}/sets/index.json`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load sets index: ${res.status}`);
  return (await res.json()) as SetsIndex;
}

export async function loadSet(file: string): Promise<SimulatorSet> {
  const res = await fetch(setsUrl(file), { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load set ${file}: ${res.status}`);
  return (await res.json()) as SimulatorSet;
}
