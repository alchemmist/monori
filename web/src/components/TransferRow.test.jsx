// @ts-nocheck
import { describe, expect, it, vi } from "vitest";
import { renderUI, screen } from "../test/render.jsx";
import TransferRow from "./TransferRow.jsx";

const names = { 1: "Card", 2: "Savings" };
const accountName = (id) => names[id];

const row = (item, props = {}) =>
    renderUI(
        <table>
            <tbody>
                <TransferRow
                    item={item}
                    accountName={accountName}
                    expanded={false}
                    onToggle={vi.fn()}
                    onSplit={vi.fn()}
                    onDelete={vi.fn()}
                    {...props}
                />
            </tbody>
        </table>,
    );

const transfer = (extra = {}) => ({
    amount: 250000,
    out: { accountId: 1, date: "2026-03-04T09:00:00", comment: "" },
    in: { accountId: 2, date: "2026-03-04T21:00:00", comment: "" },
    ...extra,
});

describe("TransferRow", () => {
    it("reads out of the source account and into the target", () => {
        row(transfer());
        expect(screen.getByText("Card")).toBeInTheDocument();
        expect(screen.getByText("Savings")).toBeInTheDocument();
    });

    it("shows the amount unsigned, so neither leg is tinted", () => {
        row(transfer());
        // 250000 kopecks -> 2 500 ₽, never -2 500
        expect(screen.getByText(/2\D?500 ₽/)).toBeInTheDocument();
        expect(screen.queryByText(/-2\D?500/)).not.toBeInTheDocument();
    });

    it("hides the second date when both legs land on the same day", () => {
        const { container } = row(transfer());
        expect(screen.getByText("04.03.2026")).toBeInTheDocument();
        expect(container.querySelector(".tx-transfer__second-date")).toBeNull();
    });

    it("shows the second date when the legs are on different days", () => {
        const { container } = row(
            transfer({
                out: { accountId: 1, date: "2026-03-04T09:00:00", comment: "" },
                in: { accountId: 2, date: "2026-03-05T09:00:00", comment: "" },
            }),
        );
        const second = container.querySelector(".tx-transfer__second-date");
        expect(second).not.toBeNull();
        expect(second).toHaveTextContent("05.03.2026");
    });

    it("shows the outgoing note, falling back to the incoming one", () => {
        row(transfer({ out: { accountId: 1, date: "2026-03-04T09:00:00", comment: "rent" } }));
        expect(screen.getByText("rent")).toBeInTheDocument();
    });

    it("falls back to the incoming comment when the outgoing leg has none", () => {
        row(
            transfer({
                out: { accountId: 1, date: "2026-03-04T09:00:00", comment: "" },
                in: { accountId: 2, date: "2026-03-04T21:00:00", comment: "from bank" },
            }),
        );
        expect(screen.getByText("from bank")).toBeInTheDocument();
    });

    it("labels the chevron by expand state", () => {
        const { rerender } = row(transfer(), { expanded: false });
        expect(screen.getByLabelText("Show both transactions")).toBeInTheDocument();
        rerender(
            <table>
                <tbody>
                    <TransferRow
                        item={transfer()}
                        accountName={accountName}
                        expanded
                        onToggle={vi.fn()}
                        onSplit={vi.fn()}
                        onDelete={vi.fn()}
                    />
                </tbody>
            </table>,
        );
        expect(screen.getByLabelText("Hide both transactions")).toBeInTheDocument();
    });

    it("toggles the expansion from the chevron button", async () => {
        const onToggle = vi.fn();
        const { user } = row(transfer(), { onToggle });
        await user.click(screen.getByLabelText("Show both transactions"));
        expect(onToggle).toHaveBeenCalledOnce();
    });
});
