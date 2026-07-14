const SPARKS = [
  "0,26 12,22 24,27 36,14 48,19 60,8 72,15 84,6 96,12 108,4",
  "0,10 14,16 28,9 42,22 56,15 70,28 84,20 98,30 112,24",
  "0,20 16,18 32,24 48,12 64,17 80,10 96,16 112,7",
];

const BARS = [14, 26, 10, 30, 18, 34, 22, 12, 28, 20];

function toBarPath(values, w, h) {
  const step = w / values.length;
  const bw = step * 0.5;
  return values.map((v, i) => {
    const x = i * step + (step - bw) / 2;
    const bh = (v / 36) * h;
    return <rect key={i} x={x} y={h - bh} width={bw} height={bh} rx="1" />;
  });
}

export default function AmbientField({ intensity = "still" }) {
  return (
    <div className={`ambient ambient_${intensity}`} aria-hidden="true">
      <svg
        className="ambient__spark ambient__spark_a"
        viewBox="0 0 108 32"
        preserveAspectRatio="none"
      >
        <polyline points={SPARKS[0]} />
      </svg>
      <svg
        className="ambient__spark ambient__spark_b"
        viewBox="0 0 112 32"
        preserveAspectRatio="none"
      >
        <polyline points={SPARKS[1]} />
      </svg>
      <svg
        className="ambient__spark ambient__spark_c"
        viewBox="0 0 112 32"
        preserveAspectRatio="none"
      >
        <polyline points={SPARKS[2]} />
      </svg>
      <svg
        className="ambient__bars ambient__bars_a"
        viewBox="0 0 120 40"
        preserveAspectRatio="none"
      >
        {toBarPath(BARS, 120, 40)}
      </svg>
      <svg
        className="ambient__bars ambient__bars_b"
        viewBox="0 0 120 40"
        preserveAspectRatio="none"
      >
        {toBarPath([...BARS].reverse(), 120, 40)}
      </svg>
      <svg className="ambient__donut" viewBox="0 0 42 42">
        <circle className="ambient__donut-track" cx="21" cy="21" r="15.9" />
        <circle
          className="ambient__donut-seg"
          cx="21"
          cy="21"
          r="15.9"
          strokeDasharray="62 38"
          strokeDashoffset="25"
        />
      </svg>
    </div>
  );
}
