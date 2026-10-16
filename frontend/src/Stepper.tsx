export type StepKey = "package" | "check" | "analyze" | "review" | "brief";

const STEPS: { key: StepKey; label: string }[] = [
  { key: "package", label: "Package" },
  { key: "check", label: "Section check" },
  { key: "analyze", label: "AI analysis" },
  { key: "review", label: "Your review" },
  { key: "brief", label: "Final brief" },
];

/** done: which steps are complete. blocked: a step that cannot proceed (for example failed section check). */
export default function Stepper({ done, blocked }: { done: Record<StepKey, boolean>; blocked?: StepKey }) {
  const current = STEPS.find((s) => !done[s.key])?.key;
  return (
    <ol className="stepper" aria-label="Progress">
      {STEPS.map((s, i) => {
        const cls = done[s.key] ? "step-done" : s.key === current ? (blocked === s.key ? "step-current step-blocked" : "step-current") : "";
        return (
          <li key={s.key} className={`step ${cls}`} data-n={i + 1} aria-current={s.key === current ? "step" : undefined}>
            {s.label}
            {done[s.key] && <span className="sr-only"> (done)</span>}
          </li>
        );
      })}
    </ol>
  );
}
