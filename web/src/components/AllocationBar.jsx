export default function AllocationBar({ amounts, total, colors, onChange }) {
    const boundaries = amounts
        .slice(0, -1)
        .map((_, index) => amounts.slice(0, index + 1).reduce((sum, amount) => sum + amount, 0));
    const stops = amounts.reduce(
        (result, amount, index) => {
            const from = result.position;
            const to = from + (amount / total) * 100;
            const color = colors[index % colors.length];
            result.colors.push(`${color} ${from}%`, `${color} ${to}%`);
            result.position = to;
            return result;
        },
        { colors: [], position: 0 },
    );

    const moveBoundary = (index, value) => {
        const previous = index === 0 ? 0 : boundaries[index - 1];
        const next = index === boundaries.length - 1 ? total : boundaries[index + 1];
        const boundary = Math.max(previous + 1, Math.min(next - 1, value));
        const nextAmounts = [...amounts];
        nextAmounts[index] = boundary - previous;
        nextAmounts[index + 1] = next - boundary;
        onChange(nextAmounts);
    };

    return (
        <div
            className="split-allocation"
            style={{ background: `linear-gradient(90deg, ${stops.colors.join(", ")})` }}
        >
            {boundaries.map((boundary, index) => (
                <input
                    key={index}
                    className="split-allocation__range"
                    type="range"
                    aria-label={`Boundary between parts ${index + 1} and ${index + 2}`}
                    min={1}
                    max={total - 1}
                    step={1}
                    value={boundary}
                    onChange={(event) => moveBoundary(index, Number(event.target.value))}
                />
            ))}
        </div>
    );
}
