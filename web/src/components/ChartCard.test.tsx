import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ChartCard, { ChartBoundary } from "./ChartCard.jsx";
import { renderUI, screen } from "../test/render.jsx";

beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("ChartCard", () => {
    it("frames its title, controls and chart body", () => {
        const { container } = renderUI(
            <ChartCard title="Spending" controls={<button>Filter</button>}>
                Chart body
            </ChartCard>,
        );
        const card = container.querySelector<HTMLElement>(".chart-card")!;
        expect(card).toHaveClass("card");
        expect(
            screen.getByText("Spending").closest<HTMLElement>(".chart-card__head")!,
        ).toBeInTheDocument();
        expect(
            screen
                .getByRole("button", { name: "Filter" })
                .closest<HTMLElement>(".chart-card__head")!,
        ).toBe(card.querySelector<HTMLElement>(".chart-card__head")!);
        expect(
            screen.getByText("Chart body").closest<HTMLElement>(".chart-card__body")!,
        ).toBeInTheDocument();
    });

    it("takes the wide and tall modifiers only when asked to", () => {
        const plain = renderUI(<ChartCard title="Plain">Body</ChartCard>);
        expect(plain.container.querySelector<HTMLElement>(".chart-card")!).not.toHaveClass(
            "chart-card_wide",
        );
        expect(plain.container.querySelector<HTMLElement>(".chart-card__body")!).not.toHaveClass(
            "chart-card__body_tall",
        );
        plain.unmount();

        const { container } = renderUI(
            <ChartCard title="Big" wide tall>
                Body
            </ChartCard>,
        );
        expect(container.querySelector<HTMLElement>(".chart-card")!).toHaveClass("chart-card_wide");
        expect(container.querySelector<HTMLElement>(".chart-card__body")!).toHaveClass(
            "chart-card__body_tall",
        );
    });

    it("catches a throwing chart without taking the surrounding card down", () => {
        const Boom = () => {
            throw new Error("bad series");
        };
        const { container } = renderUI(
            <ChartCard title="Spending">
                <Boom />
            </ChartCard>,
        );
        expect(screen.getByText("Spending")).toBeInTheDocument();
        expect(screen.getByText("No data for this chart")).toBeInTheDocument();
        expect(container.querySelector<HTMLElement>(".chart-card__body")!).toBeInTheDocument();
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

    it("greys out the fallback message", () => {
        const ThrowingComponent = () => {
            throw new Error("Chart render error");
        };

        renderUI(
            <ChartBoundary>
                <ThrowingComponent />
            </ChartBoundary>,
        );

        expect(screen.getByText("No data for this chart")).toHaveStyle({
            display: "grid",
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
