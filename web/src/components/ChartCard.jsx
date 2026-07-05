import { Component } from "react";
import { Chart } from "@gravity-ui/charts";

/** A chart that can never take the page down with it. */
class ChartBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(prev) {
    if (prev.data !== this.props.data && this.state.error) this.setState({ error: null });
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ display: "grid", placeItems: "center", height: "100%", color: "var(--m-text-faint)" }}>
          No data for this chart
        </div>
      );
    }
    return <Chart data={this.props.data} />;
  }
}

export default function ChartCard({ title, wide, tall, controls, children, data }) {
  return (
    <div className={`card chart-card ${wide ? "chart-card_wide" : ""}`}>
      <div className="chart-card__head">
        <div className="chart-card__title">{title}</div>
        {controls}
      </div>
      <div className={`chart-card__body ${tall ? "chart-card__body_tall" : ""}`}>
        {children ?? <ChartBoundary data={data} />}
      </div>
    </div>
  );
}

export { ChartBoundary };
