import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import "./timenav.css";

const H = 56;
const MIN_SPAN = 2; // minimum window = 3 months (inclusive indices)

/**
 * Overview strip over the full monthly history with a draggable, resizable
 * time window — the same idiom as a stock-chart navigator.
 *
 * @param items  [{key: 'YYYY-MM', value: number}] — full series, oldest first
 * @param range  [loIdx, hiIdx] inclusive window over items
 * @param onChange ([lo, hi]) — fired live while dragging
 */
export default function TimeNavigator({ items, range, onChange }) {
  const wrapRef = useRef(null);
  const [width, setWidth] = useState(0);
  const dragRef = useRef(null);

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const n = items.length;
  const [lo, hi] = range;
  const cellW = n > 0 ? width / n : 0;

  // Catmull-Rom through the samples, converted to cubic beziers — the strip
  // reads as a calm curve instead of a saw. Control points are clamped to the
  // plot range so the spline never dips below the baseline.
  const areaPath = useMemo(() => {
    if (!n || !width) return "";
    const max = Math.max(...items.map((d) => d.value), 1);
    const pad = 5;
    const top = pad,
      bottom = H - pad;
    const pt = (i) => {
      const j = Math.max(0, Math.min(n - 1, i));
      return [(j + 0.5) * cellW, bottom - (items[j].value / max) * (bottom - top)];
    };
    const cy = (v) => Math.max(top, Math.min(bottom, v));
    const [x0, y0] = pt(0);
    let d = `M ${x0} ${H} L ${x0} ${y0}`;
    for (let i = 0; i < n - 1; i++) {
      const [xa, ya] = pt(i - 1),
        [xb, yb] = pt(i),
        [xc, yc] = pt(i + 1),
        [xd, yd] = pt(i + 2);
      d += ` C ${xb + (xc - xa) / 6} ${cy(yb + (yc - ya) / 6)},`;
      d += ` ${xc - (xd - xb) / 6} ${cy(yc - (yd - yb) / 6)}, ${xc} ${yc}`;
    }
    d += ` L ${pt(n - 1)[0]} ${H} Z`;
    return d;
  }, [items, n, width, cellW]);

  const yearTicks = useMemo(() => {
    const ticks = [];
    for (let i = 0; i < n; i++) {
      if (items[i].key.endsWith("-01")) ticks.push({ i, year: items[i].key.slice(0, 4) });
    }
    return ticks;
  }, [items, n]);

  const clampRange = (a, b) => {
    const span = b - a;
    let na = Math.max(0, Math.min(a, n - 1 - span));
    return [na, na + span];
  };

  const startDrag = (mode) => (e) => {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { mode, startX: e.clientX, lo, hi };
  };

  const onPointerMove = (e) => {
    const d = dragRef.current;
    if (!d || !cellW) return;
    const di = Math.round((e.clientX - d.startX) / cellW);
    if (d.mode === "move") {
      onChange(clampRange(d.lo + di, d.hi + di));
    } else if (d.mode === "l") {
      onChange([Math.max(0, Math.min(d.lo + di, d.hi - MIN_SPAN)), d.hi]);
    } else if (d.mode === "r") {
      onChange([d.lo, Math.min(n - 1, Math.max(d.hi + di, d.lo + MIN_SPAN))]);
    }
  };

  const endDrag = () => {
    dragRef.current = null;
  };

  // Click on the track outside the window: center the window there and keep dragging.
  const onTrackDown = (e) => {
    if (!cellW) return;
    const rect = wrapRef.current.getBoundingClientRect();
    const i = Math.floor((e.clientX - rect.left) / cellW);
    const span = hi - lo;
    const next = clampRange(i - Math.round(span / 2), i - Math.round(span / 2) + span);
    onChange(next);
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { mode: "move", startX: e.clientX, lo: next[0], hi: next[1] };
  };

  useEffect(() => {
    const up = () => (dragRef.current = null);
    window.addEventListener("pointerup", up);
    return () => window.removeEventListener("pointerup", up);
  }, []);

  const winX = lo * cellW;
  const winW = (hi - lo + 1) * cellW;

  return (
    <div className="timenav" ref={wrapRef}>
      {width > 0 && n > 0 && (
        <svg
          width={width}
          height={H}
          className="timenav__svg"
          onPointerDown={onTrackDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
        >
          <path d={areaPath} className="timenav__area" />
          {/* ruler: minor tick per month, major tick + label per year */}
          {items.map((it, i) => (
            <line
              key={it.key}
              x1={i * cellW}
              y1={H}
              x2={i * cellW}
              y2={H - (it.key.endsWith("-01") ? 8 : 3)}
              className="timenav__tick"
            />
          ))}
          {yearTicks.map(({ i, year }) => (
            <text key={year} x={i * cellW + 4} y={11} className="timenav__year">
              {year}
            </text>
          ))}

          {/* dim everything outside the window */}
          <rect x={0} y={0} width={Math.max(winX, 0)} height={H} className="timenav__dim" />
          <rect
            x={winX + winW}
            y={0}
            width={Math.max(width - winX - winW, 0)}
            height={H}
            className="timenav__dim"
          />

          {/* the window itself */}
          <rect
            x={winX}
            y={0}
            width={winW}
            height={H}
            className="timenav__window"
            onPointerDown={startDrag("move")}
          />
          <g className="timenav__handle" onPointerDown={startDrag("l")}>
            <rect x={winX - 5} y={0} width={11} height={H} fill="transparent" />
            <rect x={winX - 1.5} y={0} width={3} height={H} className="timenav__grip" />
          </g>
          <g className="timenav__handle" onPointerDown={startDrag("r")}>
            <rect x={winX + winW - 5} y={0} width={11} height={H} fill="transparent" />
            <rect x={winX + winW - 1.5} y={0} width={3} height={H} className="timenav__grip" />
          </g>
        </svg>
      )}
    </div>
  );
}
