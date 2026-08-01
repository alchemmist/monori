import { Component } from "react";
import type { ReactNode } from "react";

interface BoundaryProps {
    children: ReactNode;
}

interface BoundaryState {
    error: Error | null;
    prevChildren: ReactNode | undefined;
}

/** An error boundary so a single bad chart can never take the page down with it. */
class ChartBoundary extends Component<BoundaryProps, BoundaryState> {
    override state: BoundaryState = { error: null, prevChildren: undefined };

    static getDerivedStateFromError(error: Error): Partial<BoundaryState> {
        return { error };
    }

    static getDerivedStateFromProps(
        props: BoundaryProps,
        state: BoundaryState,
    ): Partial<BoundaryState> | null {
        // give the chart a fresh try whenever its content changes (new data/filters)
        if (props.children !== state.prevChildren) {
            return { error: null, prevChildren: props.children };
        }
        return null;
    }

    override render() {
        if (this.state.error) {
            return (
                <div
                    style={{
                        display: "grid",
                        placeItems: "center",
                        height: "100%",
                        color: "var(--m-text-faint)",
                    }}
                >
                    No data for this chart
                </div>
            );
        }
        return this.props.children;
    }
}

interface ChartCardProps {
    title: ReactNode;
    wide?: boolean;
    tall?: boolean;
    controls?: ReactNode;
    children: ReactNode;
}

export default function ChartCard({ title, wide, tall, controls, children }: ChartCardProps) {
    return (
        <div className={`card chart-card ${wide ? "chart-card_wide" : ""}`}>
            <div className="chart-card__head">
                <div className="chart-card__title">{title}</div>
                {controls}
            </div>
            <div className={`chart-card__body ${tall ? "chart-card__body_tall" : ""}`}>
                <ChartBoundary>{children}</ChartBoundary>
            </div>
        </div>
    );
}

export { ChartBoundary };
