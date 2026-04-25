import { useState } from "react";

import type { PartGrade, QuestionGrade, QuestionRubric, RubricPart, StudentAnswer } from "../types";

interface Props {
  rubric: QuestionRubric;
  grade: QuestionGrade | null;
  onSubmit: (answers: Record<string, StudentAnswer>) => void;
  onNext: () => void;
  isLast: boolean;
  index: number;
  total: number;
}

export function QuestionCard({ rubric, grade, onSubmit, onNext, isLast, index, total }: Props) {
  const [answers, setAnswers] = useState<Record<string, StudentAnswer>>({});

  const submitted = grade !== null;

  const setAnswer = (partId: string, patch: Partial<StudentAnswer>) => {
    setAnswers((prev) => ({
      ...prev,
      [partId]: { ...(prev[partId] ?? { part_id: partId }), ...patch, part_id: partId },
    }));
  };

  return (
    <article className="mx-auto max-w-3xl space-y-5 p-6">
      <header className="space-y-1">
        <p className="text-xs uppercase tracking-wider text-slate-500">
          Question {index + 1} of {total} &middot; {rubric.max_marks} marks
        </p>
        <h2 className="text-lg font-medium text-chapter">{rubric.stem}</h2>
      </header>

      {rubric.figure_paths.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {rubric.figure_paths.map((src) => (
            <img
              key={src}
              src={src.startsWith("./") ? (import.meta.env.BASE_URL + "sets/" + src.slice(2)).replace(/\/+/g, "/") : src}
              alt="Question figure"
              className="max-h-80 rounded border border-slate-200"
            />
          ))}
        </div>
      )}

      <div className="space-y-6">
        {rubric.parts.map((part) => (
          <PartInput
            key={part.id}
            part={part}
            answer={answers[part.id]}
            partGrade={grade?.parts.find((p) => p.part_id === part.id) ?? null}
            onChange={(patch) => setAnswer(part.id, patch)}
            submitted={submitted}
          />
        ))}
      </div>

      {!submitted ? (
        <div className="flex justify-end">
          <button
            type="button"
            className="rounded-lg bg-chapter px-4 py-2 font-medium text-white shadow-sm hover:bg-slate-700"
            onClick={() => onSubmit(answers)}
          >
            Check my answer
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <GradeBadge grade={grade!} />
          <div className="flex justify-end">
            <button
              type="button"
              className="rounded-lg bg-chapter px-4 py-2 font-medium text-white shadow-sm hover:bg-slate-700"
              onClick={onNext}
            >
              {isLast ? "See score" : "Next question"}
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

function PartInput({
  part,
  answer,
  partGrade,
  onChange,
  submitted,
}: {
  part: RubricPart;
  answer: StudentAnswer | undefined;
  partGrade: PartGrade | null;
  onChange: (patch: Partial<StudentAnswer>) => void;
  submitted: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between">
        <p className="font-medium text-chapter">
          ({part.id}) {part.prompt}
        </p>
        <span className="text-xs text-slate-500">{part.max_marks} mark{part.max_marks === 1 ? "" : "s"}</span>
      </div>

      <div className="mt-3">
        {part.answer_type === "mcq" ? (
          <fieldset className="space-y-2">
            {(part.mcq_options ?? []).map((opt) => (
              <label
                key={opt.label}
                className="flex cursor-pointer items-start gap-2 rounded-md border border-slate-200 p-2 hover:border-chapter"
              >
                <input
                  type="radio"
                  name={`mcq-${part.id}`}
                  className="mt-1"
                  checked={answer?.mcq_label === opt.label}
                  disabled={submitted}
                  onChange={() => onChange({ mcq_label: opt.label })}
                />
                <span>
                  <b>{opt.label}.</b> {opt.text}
                </span>
              </label>
            ))}
          </fieldset>
        ) : part.answer_type === "numeric" ? (
          <div className="flex items-center gap-2">
            <input
              type="text"
              inputMode="decimal"
              placeholder="e.g. 0.25"
              disabled={submitted}
              className="w-48 rounded border border-slate-300 px-3 py-2"
              value={answer?.text ?? ""}
              onChange={(e) => onChange({ text: e.target.value })}
            />
            {part.numeric_unit && (
              <span className="text-slate-500">
                unit expected: <b>{part.numeric_unit}</b>
              </span>
            )}
          </div>
        ) : part.answer_type === "self_check" ? (
          <SelfCheck part={part} answer={answer} onChange={onChange} submitted={submitted} />
        ) : (
          <textarea
            rows={part.answer_type === "free_text" ? 6 : 2}
            className="w-full rounded border border-slate-300 px-3 py-2"
            placeholder={part.answer_type === "short_text" ? "Your answer" : "Explain your reasoning"}
            disabled={submitted}
            value={answer?.text ?? ""}
            onChange={(e) => onChange({ text: e.target.value })}
          />
        )}
      </div>

      {submitted && partGrade && <PartFeedback part={part} grade={partGrade} />}
    </div>
  );
}

function SelfCheck({
  part,
  answer,
  onChange,
  submitted,
}: {
  part: RubricPart;
  answer: StudentAnswer | undefined;
  onChange: (patch: Partial<StudentAnswer>) => void;
  submitted: boolean;
}) {
  const ticked = new Set(answer?.self_check_concepts ?? []);
  const toggle = (c: string) => {
    const next = new Set(ticked);
    if (next.has(c)) next.delete(c);
    else next.add(c);
    onChange({ self_check_concepts: [...next] });
  };
  return (
    <div className="space-y-3">
      <textarea
        rows={5}
        className="w-full rounded border border-slate-300 px-3 py-2"
        placeholder="Write your full answer here."
        disabled={submitted}
        value={answer?.text ?? ""}
        onChange={(e) => onChange({ text: e.target.value })}
      />
      <p className="text-sm font-medium text-chapter">
        After writing, tick the points you covered:
      </p>
      <ul className="space-y-1 text-sm">
        {part.required_working_concepts.map((c) => (
          <li key={c.concept}>
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="checkbox"
                className="mt-1"
                checked={ticked.has(c.concept)}
                disabled={submitted}
                onChange={() => toggle(c.concept)}
              />
              <span>
                <b>{c.marks} mark{c.marks === 1 ? "" : "s"}:</b> {c.concept}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PartFeedback({ part, grade }: { part: RubricPart; grade: PartGrade }) {
  const color =
    grade.verdict === "correct"
      ? "border-correct bg-green-50 text-green-900"
      : grade.verdict === "partial"
        ? "border-partial bg-amber-50 text-amber-900"
        : grade.verdict === "self_check"
          ? "border-slate-300 bg-slate-50 text-slate-900"
          : "border-incorrect bg-red-50 text-red-900";

  const verdictLabel =
    grade.verdict === "self_check"
      ? "Self-check"
      : grade.verdict === "correct"
        ? "Correct"
        : grade.verdict === "partial"
          ? "Partial credit"
          : "Not yet";

  return (
    <div className={`mt-4 rounded-md border p-3 ${color}`}>
      <p className="text-sm">
        <b>{verdictLabel}:</b> {grade.marks_awarded} / {grade.max_marks} marks
      </p>

      {grade.concepts.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {grade.concepts.map((c) => (
            <li key={c.concept}>
              {c.hit ? "\u2713" : "\u2717"}{" "}
              <span className={c.hit ? "" : "text-slate-500"}>{c.concept}</span>{" "}
              <span className="text-slate-500">
                ({c.awarded}/{c.marks})
              </span>
            </li>
          ))}
        </ul>
      )}

      {grade.triggered_mistakes.length > 0 && (
        <div className="mt-3 space-y-1 text-sm">
          {grade.triggered_mistakes.map((m, i) => (
            <p key={i}>
              <b>Heads up:</b> {m.feedback}
            </p>
          ))}
        </div>
      )}

      <div className="mt-3 rounded-md bg-white/70 p-3 text-sm">
        <p className="font-medium">Model answer:</p>
        <div
          className="prose-answer mt-1 text-slate-800"
          dangerouslySetInnerHTML={{ __html: part.model_answer_html }}
        />
        {grade.chapter_refs.length > 0 && (
          <p className="mt-2 text-xs text-slate-500">
            From your chapter: {grade.chapter_refs.join("; ")}
          </p>
        )}
      </div>
    </div>
  );
}

function GradeBadge({ grade }: { grade: QuestionGrade }) {
  if (grade.verdict === "self_check") {
    return (
      <div className="rounded-md bg-slate-100 p-3 text-sm text-slate-700">
        You graded this one yourself: <b>{grade.marks_awarded}</b> of <b>{grade.max_marks}</b>
        . Take another look at the model answer above.
      </div>
    );
  }
  const cls =
    grade.verdict === "correct"
      ? "bg-green-100 text-green-900"
      : grade.verdict === "partial"
        ? "bg-amber-100 text-amber-900"
        : "bg-red-100 text-red-900";
  return (
    <div className={`rounded-md p-3 text-sm ${cls}`}>
      <b>
        {grade.verdict === "correct"
          ? "Correct!"
          : grade.verdict === "partial"
            ? "Partial credit."
            : "Not yet."}
      </b>{" "}
      {grade.marks_awarded} of {grade.max_marks} marks.
    </div>
  );
}
