import type { QuestionGrade, SimulatorSet } from "../types";

interface Props {
  set: SimulatorSet;
  grades: QuestionGrade[];
  onRestart: () => void;
  onPickAnother: () => void;
}

export function ScoreSummary({ set, grades, onRestart, onPickAnother }: Props) {
  const totalAwarded = grades.reduce((s, g) => s + g.marks_awarded, 0);
  const totalMax = grades.reduce((s, g) => s + g.max_marks, 0);
  const pct = totalMax === 0 ? 0 : Math.round((totalAwarded / totalMax) * 100);

  const byTopic: Record<string, { awarded: number; max: number }> = {};
  for (const grade of grades) {
    const rubric = set.questions.find((q) => q.question_id === grade.question_id);
    if (!rubric) continue;
    for (const part of rubric.parts) {
      for (const ref of part.chapter_refs) {
        const bucket = byTopic[ref] ?? { awarded: 0, max: 0 };
        const pg = grade.parts.find((p) => p.part_id === part.id);
        bucket.awarded += pg?.marks_awarded ?? 0;
        bucket.max += part.max_marks;
        byTopic[ref] = bucket;
      }
    }
  }

  return (
    <section className="mx-auto max-w-2xl space-y-6 p-6">
      <header>
        <h2 className="text-2xl font-bold text-chapter">Well done!</h2>
        <p className="mt-1 text-slate-600 capitalize">
          {set.subject} &middot; {set.chapter}
        </p>
      </header>

      <div className="rounded-lg bg-white p-5 shadow-sm">
        <p className="text-lg font-medium">
          You scored{" "}
          <span className="font-bold text-chapter">
            {totalAwarded} / {totalMax}
          </span>{" "}
          ({pct}%)
        </p>
        <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full bg-correct"
            style={{ width: `${pct}%` }}
            aria-hidden="true"
          />
        </div>
      </div>

      {Object.keys(byTopic).length > 0 && (
        <div className="rounded-lg bg-white p-5 shadow-sm">
          <p className="font-medium text-chapter">By topic</p>
          <ul className="mt-3 space-y-2 text-sm">
            {Object.entries(byTopic)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([topic, b]) => (
                <li key={topic} className="flex items-center justify-between">
                  <span className="truncate pr-4">{topic}</span>
                  <span className="whitespace-nowrap font-medium">
                    {b.awarded} / {b.max}
                  </span>
                </li>
              ))}
          </ul>
        </div>
      )}

      <div className="flex gap-3">
        <button
          type="button"
          className="rounded-lg bg-chapter px-4 py-2 font-medium text-white shadow-sm hover:bg-slate-700"
          onClick={onRestart}
        >
          Try again
        </button>
        <button
          type="button"
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 font-medium text-chapter shadow-sm hover:bg-slate-50"
          onClick={onPickAnother}
        >
          Pick another chapter
        </button>
      </div>
    </section>
  );
}
