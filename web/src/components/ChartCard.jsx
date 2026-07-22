import { Component } from "react";

/** An error boundary so a single bad chart can never take the page down with it. */
class ChartBoundary extends Component {
    state = { error: null, prevChildren: undefined };

    static getDerivedStateFromError(error) {
        return { error };
    }

    static getDerivedStateFromProps(props, state) {
        // give the chart a fresh try whenever its content changes (new data/filters)
        if (props.children !== state.prevChildren) {
            return { error: null, prevChildren: props.children };
        }
        return null;
    }

    render() {
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

export default function ChartCard({ title, wide, tall, controls, children }) {
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
