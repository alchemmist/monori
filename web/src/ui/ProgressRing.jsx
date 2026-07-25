import "./progressRing.css";

const SIZE = 14;
const STROKE = 2.5;
const R = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * R;

const prefersReducedMotion = () =>
    typeof window !== "undefined" &&
    (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);

/**
 * A small determinate ring for background work. Under `prefers-reduced-motion`
 * the ring is replaced by the plain percentage, so nothing spins or sweeps.
 */
export default function ProgressRing({ value, label }) {
    const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
    if (prefersReducedMotion()) {
        return (
            <span className="progress-ring" role="status" aria-label={label} title={label}>
                {pct}%
            </span>
        );
    }
    return (
        <span className="progress-ring" role="status" aria-label={label} title={label}>
            <svg
                className="progress-ring__svg"
                width={SIZE}
                height={SIZE}
                viewBox={`0 0 ${SIZE} ${SIZE}`}
                aria-hidden="true"
            >
                <circle
                    className="progress-ring__track"
                    cx={SIZE / 2}
                    cy={SIZE / 2}
                    r={R}
                    fill="none"
                    strokeWidth={STROKE}
                />
                <circle
                    className="progress-ring__value"
                    cx={SIZE / 2}
                    cy={SIZE / 2}
                    r={R}
                    fill="none"
                    strokeWidth={STROKE}
                    strokeLinecap="round"
                    strokeDasharray={CIRCUMFERENCE}
                    strokeDashoffset={CIRCUMFERENCE * (1 - pct / 100)}
                />
            </svg>
            {pct}%
        </span>
    );
}
