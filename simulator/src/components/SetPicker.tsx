import { useEffect, useState } from "react";

import { loadIndex } from "../lib/loader";
import type { SetsIndex } from "../types";

interface Props {
  onPick: (file: string) => void;
}

export function SetPicker({ onPick }: Props) {
  const [index, setIndex] = useState<SetsIndex | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadIndex()
      .then(setIndex)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-xl rounded-lg bg-red-50 p-4 text-red-900">
        <p className="font-medium">No practice sets available yet.</p>
        <p className="mt-1 text-sm">
          Run <code className="rounded bg-red-100 px-1">igcse build-simulator</code> then deploy.
        </p>
        <p className="mt-2 text-xs text-red-700">Details: {error}</p>
      </div>
    );
  }

  if (!index) return <div className="p-6 text-slate-500">Loading practice sets...</div>;

  if (index.sets.length === 0) {
    return (
      <div className="mx-auto max-w-xl rounded-lg bg-amber-50 p-4 text-amber-900">
        <p className="font-medium">No practice sets yet.</p>
        <p className="mt-1 text-sm">
          Build one with <code className="rounded bg-amber-100 px-1">igcse build-simulator</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-3xl font-bold text-chapter">IGCSE practice simulator</h1>
      <p className="mt-2 text-slate-600">
        Pick a chapter to practise. Answers are graded instantly in your browser. Nothing you type
        leaves this page.
      </p>
      <ul className="mt-6 space-y-3">
        {index.sets.map((s) => (
          <li key={s.file}>
            <button
              type="button"
              onClick={() => onPick(s.file)}
              className="w-full rounded-lg border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-chapter hover:shadow"
            >
              <div className="flex items-baseline justify-between">
                <div>
                  <p className="font-semibold capitalize text-chapter">
                    {s.subject}: {s.chapter}
                  </p>
                  <p className="text-sm text-slate-500">
                    {s.question_count} questions &middot; generated {s.generated_at}
                  </p>
                </div>
                <span className="text-chapter" aria-hidden="true">
                  Start &rarr;
                </span>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
