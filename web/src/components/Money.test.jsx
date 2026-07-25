import { describe, expect, it } from "vitest";
import { Money, BalancePill } from "./Money.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("Money", () => {
    it("renders positive amount with rub formatting", () => {
        const { container } = renderUI(<Money value={123456} />);
        const span = container.querySelector("span.money");
        expect(span).toBeInTheDocument();
        expect(span.textContent).toMatch(/1.*235/);
    });

    it("renders negative amount correctly", () => {
        const { container } = renderUI(<Money value={-567890} />);
        const span = container.querySelector("span.money");
        expect(span).toBeInTheDocument();
        expect(span.textContent).toMatch(/-5.*679/);
    });

    it("renders zero as a span", () => {
        const { container } = renderUI(<Money value={0} />);
        expect(container.querySelector("span.money_zero")).toBeInTheDocument();
    });

    it("dims zero by default (zeroDim=true)", () => {
        const { container } = renderUI(<Money value={0} />);
        expect(container.querySelector("span.money_zero")).toBeInTheDocument();
    });

    it("does not dim zero when zeroDim=false", () => {
        const { container } = renderUI(<Money value={0} zeroDim={false} />);
        expect(container.querySelector("span.money_zero")).not.toBeInTheDocument();
    });

    it("applies signColor class for positive value when signColor=true", () => {
        const { container } = renderUI(<Money value={100000} signColor />);
        expect(container.querySelector("span.money_pos")).toBeInTheDocument();
    });

    it("applies signColor class for negative value when signColor=true", () => {
        const { container } = renderUI(<Money value={-100000} signColor />);
        expect(container.querySelector("span.money_neg")).toBeInTheDocument();
    });

    it("does not apply signColor class when signColor=false", () => {
        const { container } = renderUI(<Money value={100000} signColor={false} />);
        expect(container.querySelector("span.money_pos")).not.toBeInTheDocument();
    });

    it("renders with num class", () => {
        const { container } = renderUI(<Money value={100000} />);
        expect(container.querySelector("span.num")).toBeInTheDocument();
    });

    it("handles large positive values", () => {
        const { container } = renderUI(<Money value={123456789} />);
        const span = container.querySelector("span.money");
        expect(span.textContent).toMatch(/1.*234.*568/);
    });

    it("handles small negative values", () => {
        const { container } = renderUI(<Money value={-1} />);
        const span = container.querySelector("span.money");
        expect(span.textContent).toContain("₽");
    });

    it("rounds correctly for fractional kopecks", () => {
        const { container } = renderUI(<Money value={12345} />);
        const span = container.querySelector("span.money");
        expect(span.textContent).toMatch(/123/);
    });
});

describe("BalancePill", () => {
    it("renders positive value with pos class", () => {
        const { container } = renderUI(<BalancePill value={500000} />);
        expect(container.querySelector("span.balance-pill_pos")).toBeInTheDocument();
    });

    it("renders negative value with neg class", () => {
        const { container } = renderUI(<BalancePill value={-500000} />);
        expect(container.querySelector("span.balance-pill_neg")).toBeInTheDocument();
    });

    it("renders zero with zero class", () => {
        const { container } = renderUI(<BalancePill value={0} />);
        expect(container.querySelector("span.balance-pill_zero")).toBeInTheDocument();
    });

    it("applies num class", () => {
        const { container } = renderUI(<BalancePill value={100000} />);
        expect(container.querySelector("span.num")).toBeInTheDocument();
    });

    it("formats positive value correctly", () => {
        const { container } = renderUI(<BalancePill value={123456} />);
        const span = container.querySelector("span.balance-pill_pos");
        expect(span.textContent).toMatch(/1.*235/);
    });

    it("formats negative value correctly", () => {
        const { container } = renderUI(<BalancePill value={-987654} />);
        const span = container.querySelector("span.balance-pill_neg");
        expect(span.textContent).toMatch(/-9.*877/);
    });

    it("formats zero as rubles", () => {
        const { container } = renderUI(<BalancePill value={0} />);
        const span = container.querySelector("span.balance-pill_zero");
        expect(span.textContent).toMatch(/0/);
    });
});
