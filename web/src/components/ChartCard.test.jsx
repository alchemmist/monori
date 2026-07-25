import { describe, expect, it } from "vitest";
import ChartCard, { ChartBoundary } from "./ChartCard.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("ChartCard", () => {
    it("renders title", () => {
        renderUI(<ChartCard title="Test Chart">Content</ChartCard>);
        expect(screen.getByText("Test Chart")).toBeInTheDocument();
    });

    it("renders children content", () => {
        renderUI(<ChartCard title="Test">Hello World</ChartCard>);
        expect(screen.getByText("Hello World")).toBeInTheDocument();
    });

    it("applies card class", () => {
        const { container } = renderUI(<ChartCard title="Test">Content</ChartCard>);
        expect(container.querySelector("div.card")).toBeInTheDocument();
    });

    it("applies chart-card class", () => {
        const { container } = renderUI(<ChartCard title="Test">Content</ChartCard>);
        expect(container.querySelector("div.chart-card")).toBeInTheDocument();
    });

    it("applies chart-card_wide class when wide prop is true", () => {
        const { container } = renderUI(
            <ChartCard title="Test" wide>
                Content
            </ChartCard>,
        );
        expect(container.querySelector("div.chart-card_wide")).toBeInTheDocument();
    });

    it("does not apply chart-card_wide class when wide prop is false", () => {
        const { container } = renderUI(<ChartCard title="Test">Content</ChartCard>);
        expect(container.querySelector("div.chart-card_wide")).not.toBeInTheDocument();
    });

    it("applies chart-card__body_tall class when tall prop is true", () => {
        const { container } = renderUI(
            <ChartCard title="Test" tall>
                Content
            </ChartCard>,
        );
        expect(container.querySelector("div.chart-card__body_tall")).toBeInTheDocument();
    });

    it("does not apply chart-card__body_tall class when tall prop is false", () => {
        const { container } = renderUI(<ChartCard title="Test">Content</ChartCard>);
        expect(container.querySelector("div.chart-card__body_tall")).not.toBeInTheDocument();
    });

    it("renders controls when provided", () => {
        renderUI(
            <ChartCard title="Test" controls={<button>Filter</button>}>
                Content
            </ChartCard>,
        );
        expect(screen.getByRole("button", { name: "Filter" })).toBeInTheDocument();
    });

    it("wraps children in ChartBoundary", () => {
        const { container } = renderUI(<ChartCard title="Test">Test Content</ChartCard>);
        expect(container.querySelector("div.chart-card__body")).toBeInTheDocument();
        expect(screen.getByText("Test Content")).toBeInTheDocument();
    });

    it("renders title in chart-card__head", () => {
        const { container } = renderUI(<ChartCard title="Test Title">Content</ChartCard>);
        const title = screen.getByText("Test Title");
        expect(title.closest(".chart-card__head")).toBeInTheDocument();
    });

    it("renders title in chart-card__title", () => {
        const { container } = renderUI(<ChartCard title="Test Title">Content</ChartCard>);
        const title = screen.getByText("Test Title");
        expect(title.classList.contains("chart-card__title")).toBe(true);
    });

    it("combines wide and tall classes", () => {
        const { container } = renderUI(
            <ChartCard title="Test" wide tall>
                Content
            </ChartCard>,
        );
        expect(container.querySelector("div.chart-card_wide")).toBeInTheDocument();
        expect(container.querySelector("div.chart-card__body_tall")).toBeInTheDocument();
    });
});

describe("ChartBoundary", () => {
    it("renders children when no error", () => {
        renderUI(
            <ChartBoundary>
                <div>Chart Content</div>
            </ChartBoundary>,
        );
        expect(screen.getByText("Chart Content")).toBeInTheDocument();
    });

    it("displays fallback message when error occurs in child", () => {
        const ThrowingComponent = () => {
            throw new Error("Chart render error");
        };

        renderUI(
            <ChartBoundary>
                <ThrowingComponent />
            </ChartBoundary>,
        );

        expect(screen.getByText("No data for this chart")).toBeInTheDocument();
    });

    it("recovers from error when children change", () => {
        const { rerender } = renderUI(
            <ChartBoundary>
                <div>First Content</div>
            </ChartBoundary>,
        );

        expect(screen.getByText("First Content")).toBeInTheDocument();

        rerender(
            <ChartBoundary>
                <div>Second Content</div>
            </ChartBoundary>,
        );

        expect(screen.queryByText("No data for this chart")).not.toBeInTheDocument();
        expect(screen.getByText("Second Content")).toBeInTheDocument();
    });

    it("applies correct styling to error message", () => {
        const ThrowingComponent = () => {
            throw new Error("Chart render error");
        };

        const { container } = renderUI(
            <ChartBoundary>
                <ThrowingComponent />
            </ChartBoundary>,
        );

        const errorDiv = container.querySelector("div");
        expect(errorDiv).toHaveStyle({ display: "grid" });
    });

    it("error message has faint text color", () => {
        const ThrowingComponent = () => {
            throw new Error("Chart render error");
        };

        renderUI(
            <ChartBoundary>
                <ThrowingComponent />
            </ChartBoundary>,
        );

        expect(screen.getByText("No data for this chart")).toHaveStyle({
            color: "var(--m-text-faint)",
        });
    });

    it("resets error state on props change", () => {
        let shouldThrow = true;
        const ConditionalComponent = () => {
            if (shouldThrow) throw new Error("error");
            return <div>Success</div>;
        };

        const { rerender } = renderUI(
            <ChartBoundary>
                <ConditionalComponent />
            </ChartBoundary>,
        );

        expect(screen.getByText("No data for this chart")).toBeInTheDocument();

        shouldThrow = false;
        rerender(
            <ChartBoundary>
                <ConditionalComponent />
            </ChartBoundary>,
        );

        expect(screen.getByText("Success")).toBeInTheDocument();
        expect(screen.queryByText("No data for this chart")).not.toBeInTheDocument();
    });
});
