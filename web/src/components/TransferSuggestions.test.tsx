import { beforeEach, describe, expect, it, vi } from "vitest";
import TransferSuggestions from "./TransferSuggestions.jsx";
import { renderUI, resetStore, screen, seed, tx, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import type { Transaction, TransferSuggestion } from "../types.js";

const accounts = [
    { id: 1, name: "Card", archived: false },
    { id: 2, name: "Cash", archived: false },
];

const outTx = tx(10, {
    accountId: 1,
    amount: -5000,
    description: "ATM out",
    date: "2026-03-01T00:00:00",
});
const inTx = tx(11, {
    accountId: 2,
    amount: 5000,
    description: "ATM in",
    date: "2026-03-03T00:00:00",
});

const pair = {
    outTxId: 10,
    inTxId: 11,
    amount: 5000,
    days: 2,
    mismatch: false,
};

function stub({
    suggestions,
    detect,
}: {
    suggestions?: { rows: TransferSuggestion[]; transactions: Transaction[] };
    detect?: { merged: string[]; suggested: number };
} = {}) {
    const detectTransfers = vi
        .spyOn(useStore.getState(), "detectTransfers")
        .mockResolvedValue(detect ?? { merged: [], suggested: 0 });
    const transferSuggestions = vi
        .spyOn(useStore.getState(), "transferSuggestions")
        .mockResolvedValue(suggestions ?? { rows: [pair], transactions: [outTx, inTx] });
    const linkTransfer = vi
        .spyOn(useStore.getState(), "linkTransfer")
        .mockResolvedValue("transfer-1");
    const dismissTransferSuggestion = vi
        .spyOn(useStore.getState(), "dismissTransferSuggestion")
        .mockResolvedValue();
    const notify = vi.spyOn(useStore.getState(), "notify");
    return {
        detectTransfers,
        transferSuggestions,
        linkTransfer,
        dismissTransferSuggestion,
        notify,
    };
}

describe("TransferSuggestions", () => {
    beforeEach(() => {
        resetStore();
        seed({ accounts });
    });

    const render = (props = {}) => renderUI(<TransferSuggestions onClose={vi.fn()} {...props} />);

    it("scans, then lists a suggested pair with its route and dates", async () => {
        stub();
        render();
        expect(screen.getByText("Looking for pairs…")).toBeInTheDocument();
        expect(await screen.findByText("Card")).toBeInTheDocument();
        expect(screen.getByText("Cash")).toBeInTheDocument();
        expect(screen.getByText("2 days apart", { exact: false })).toBeInTheDocument();
        expect(screen.getByText("ATM out → ATM in")).toBeInTheDocument();
    });

    it("reports how many pairs a scan merged unasked", async () => {
        stub({
            detect: { merged: ["t1"], suggested: 0 },
            suggestions: { rows: [], transactions: [] },
        });
        render();
        expect(
            await screen.findByText("1 pair was merged automatically just now."),
        ).toBeInTheDocument();
        expect(screen.getByText("Nothing else needs confirming.")).toBeInTheDocument();
    });

    it("pluralizes the merged-count line", async () => {
        stub({
            detect: { merged: ["t1", "t2"], suggested: 0 },
            suggestions: { rows: [pair], transactions: [outTx, inTx] },
        });
        render();
        expect(
            await screen.findByText("2 pairs were merged automatically just now."),
        ).toBeInTheDocument();
    });

    it("shows the full empty explanation when a scan merged nothing", async () => {
        stub({ suggestions: { rows: [], transactions: [] } });
        render();
        expect(await screen.findByText(/Nothing to merge/)).toBeInTheDocument();
    });

    it("merges a pair, removing it from the list", async () => {
        const { linkTransfer } = stub();
        const { user } = render();
        await screen.findByText("Card");
        await user.click(screen.getByRole("button", { name: "Merge" }));
        await waitFor(() => expect(linkTransfer).toHaveBeenCalledWith(10, 11));
        await waitFor(() => expect(screen.queryByRole("button", { name: "Merge" })).toBeNull());
    });

    it("dismisses a pair, removing it from the list", async () => {
        const { dismissTransferSuggestion } = stub();
        const { user } = render();
        await screen.findByText("Card");
        await user.click(screen.getByRole("button", { name: "Not a transfer" }));
        await waitFor(() => expect(dismissTransferSuggestion).toHaveBeenCalledWith(10, 11));
        await waitFor(() =>
            expect(screen.queryByRole("button", { name: "Not a transfer" })).toBeNull(),
        );
    });

    it("notifies when a mutation fails and keeps the pair", async () => {
        const s = stub();
        s.linkTransfer.mockRejectedValue(new Error("offline"));
        const { user } = render();
        await screen.findByText("Card");
        await user.click(screen.getByRole("button", { name: "Merge" }));
        await waitFor(() =>
            expect(s.notify).toHaveBeenCalledWith({
                title: "Failed to update the pair",
                theme: "danger",
                content: "Error: offline",
            }),
        );
        expect(screen.getByRole("button", { name: "Merge" })).toBeInTheDocument();
    });

    it("notifies when the suggestion fetch fails", async () => {
        const s = stub();
        s.transferSuggestions.mockRejectedValue(new Error("down"));
        render();
        await waitFor(() =>
            expect(s.notify).toHaveBeenCalledWith({
                title: "Failed to look for transfers",
                theme: "danger",
                content: "Error: down",
            }),
        );
        expect(await screen.findByText(/Nothing to merge/)).toBeInTheDocument();
    });

    it("still refreshes when the initial scan fails", async () => {
        const s = stub();
        s.detectTransfers.mockRejectedValue(new Error("scan down"));
        render();
        expect(await screen.findByText("Card")).toBeInTheDocument();
        expect(s.transferSuggestions).toHaveBeenCalled();
    });

    it("skips rows whose transactions are missing and falls back for unknown accounts", async () => {
        const ghost = { outTxId: 20, inTxId: 21, amount: 1000, days: 1, mismatch: false };
        const oddAccount = tx(30, {
            accountId: 99,
            amount: -700,
            description: "",
            date: "2026-03-01T00:00:00",
        });
        const oddIn = tx(31, {
            accountId: 99,
            amount: 700,
            description: "",
            date: "2026-03-02T00:00:00",
        });
        stub({
            suggestions: {
                rows: [ghost, { outTxId: 30, inTxId: 31, amount: 700, days: 1, mismatch: true }],
                transactions: [oddAccount, oddIn],
            },
        });
        render();
        await screen.findByText("1 day apart", { exact: false });
        expect(screen.getAllByText("—").length).toBeGreaterThan(0);
        expect(screen.getByRole("button", { name: "Merge" })).toBeInTheDocument();
    });

    it("closes via the Done action", async () => {
        stub({ suggestions: { rows: [], transactions: [] } });
        const close = vi.fn();
        const { user } = render({ onClose: close });
        await screen.findByText(/Nothing to merge/);
        await user.click(screen.getByRole("button", { name: "Done" }));
        expect(close).toHaveBeenCalled();
    });
});
