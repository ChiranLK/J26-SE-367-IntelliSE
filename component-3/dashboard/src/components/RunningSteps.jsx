import { useEffect, useState } from "react";

// Demo pacing: how long a step-by-step run stays on screen so the work is visible (none in tests).
export const RUN_PACE_MS = import.meta.env.MODE === "test" ? 0 : 10000;

// A different length for every run, between 10 and 20 seconds (none in tests).
export const randomPaceMs = () => (import.meta.env.MODE === "test" ? 0 : 10000 + Math.floor(Math.random() * 10001));

export const pace = (startedAt, minimumMs = RUN_PACE_MS) => {
  const remaining = minimumMs - (Date.now() - startedAt);
  return remaining > 0 ? new Promise((resolve) => setTimeout(resolve, remaining)) : Promise.resolve();
};

// A short list of steps that tick over while a request is running.
export function RunningSteps({ steps, startedAt, label = "Progress", durationMs = RUN_PACE_MS }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 300);
    return () => clearInterval(timer);
  }, []);
  const active = Math.min(steps.length - 1, Math.floor((now - (startedAt ?? now)) / (durationMs / steps.length || 800)));
  return (
    <ol className="gen-steps val-steps" aria-label={label}>
      {steps.map((step, index) => (
        <li key={step} className={index < active ? "step-done" : index === active ? "step-active" : "step-wait"}>
          {index < active ? "✓" : index === active ? "…" : "○"} {step}
        </li>
      ))}
    </ol>
  );
}
