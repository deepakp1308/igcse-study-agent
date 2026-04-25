import { useCallback, useEffect, useState } from "react";

import { QuestionCard } from "./components/QuestionCard";
import { ScoreSummary } from "./components/ScoreSummary";
import { SetPicker } from "./components/SetPicker";
import { browserEmbeddings, embeddingsAvailable } from "./lib/embeddings";
import { gradeQuestion } from "./lib/grade";
import { loadSet } from "./lib/loader";
import type { QuestionGrade, SimulatorSet, StudentAnswer } from "./types";

type Phase = "pick" | "quiz" | "done";

function getSetParam(): string | null {
  try {
    const url = new URL(window.location.href);
    return url.searchParams.get("set");
  } catch {
    return null;
  }
}

function setSetParam(file: string | null) {
  try {
    const url = new URL(window.location.href);
    if (file) url.searchParams.set("set", file);
    else url.searchParams.delete("set");
    window.history.replaceState({}, "", url.toString());
  } catch {
    // ignore
  }
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("pick");
  const [set, setSet] = useState<SimulatorSet | null>(null);
  const [grades, setGrades] = useState<QuestionGrade[]>([]);
  const [idx, setIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const embedder = embeddingsAvailable() ? browserEmbeddings : undefined;

  const startSet = useCallback(async (file: string) => {
    setError(null);
    try {
      const s = await loadSet(file);
      setSet(s);
      setGrades([]);
      setIdx(0);
      setPhase("quiz");
      setSetParam(file);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  // auto-start if ?set=<file> present
  useEffect(() => {
    const f = getSetParam();
    if (f && phase === "pick") void startSet(f);
  }, [phase, startSet]);

  const onSubmit = useCallback(
    async (answers: Record<string, StudentAnswer>) => {
      if (!set) return;
      const rubric = set.questions[idx];
      const grade = await gradeQuestion(rubric, answers, embedder);
      setGrades((prev) => {
        const next = [...prev];
        next[idx] = grade;
        return next;
      });
    },
    [set, idx, embedder],
  );

  const onNext = useCallback(() => {
    if (!set) return;
    if (idx + 1 >= set.questions.length) setPhase("done");
    else setIdx((i) => i + 1);
  }, [set, idx]);

  const onRestart = useCallback(() => {
    setGrades([]);
    setIdx(0);
    setPhase("quiz");
  }, []);

  const onPickAnother = useCallback(() => {
    setSet(null);
    setGrades([]);
    setIdx(0);
    setPhase("pick");
    setSetParam(null);
  }, []);

  return (
    <div className="min-h-full bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-4xl px-6 py-3 text-sm text-slate-500">
          <span className="font-semibold text-chapter">IGCSE Practice</span>
          <span className="mx-2" aria-hidden="true">&middot;</span>
          <span>No keys, no tracking. Everything runs in your browser.</span>
        </div>
      </header>

      {error && (
        <div className="mx-auto mt-4 max-w-xl rounded-md bg-red-50 p-3 text-sm text-red-900">
          {error}
        </div>
      )}

      {phase === "pick" && <SetPicker onPick={startSet} />}

      {phase === "quiz" && set && (
        <QuestionCard
          key={idx}
          rubric={set.questions[idx]}
          grade={grades[idx] ?? null}
          onSubmit={onSubmit}
          onNext={onNext}
          isLast={idx === set.questions.length - 1}
          index={idx}
          total={set.questions.length}
        />
      )}

      {phase === "done" && set && (
        <ScoreSummary
          set={set}
          grades={grades}
          onRestart={onRestart}
          onPickAnother={onPickAnother}
        />
      )}
    </div>
  );
}
