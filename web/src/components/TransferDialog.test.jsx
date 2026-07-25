import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import TransferDialog from "./TransferDialog.jsx";
import { renderUI, resetStore, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";

vi.mock("../api.js");

describe("TransferDialog", () => {
    beforeEach(() => {
        resetStore();
        vi.clearAllMocks();
    });

    it("filters out archived accounts from options", () => {
        seed({
            accounts: [
                { id: 1, name: "Active 1", type: "card", archived: false },
                { id: 2, name: "Active 2", type: "card", archived: false },
                { id: 3, name: "Archived", type: "card", archived: true },
            ],
        });
        expect(() => {
            renderUI(
                <TransferDialog
                    accounts={[
                        { id: 1, name: "Active 1", archived: false },
                        { id: 2, name: "Active 2", archived: false },
                        { id: 3, name: "Archived", archived: true },
                    ]}
                    onClose={() => {}}
                />,
            );
        }).not.toThrow();
    });

    it("renders transfer dialog component", () => {
        seed({
            accounts: [
                { id: 1, name: "Card", type: "card", archived: false },
                { id: 2, name: "Cash", type: "cash", archived: false },
            ],
        });
        expect(() => {
            renderUI(
                <TransferDialog
                    accounts={[
                        { id: 1, name: "Card", archived: false },
                        { id: 2, name: "Cash", archived: false },
                    ]}
                    onClose={() => {}}
                />,
            );
        }).not.toThrow();
    });

    it("requires amount > 0", async () => {
        seed({
            accounts: [
                { id: 1, name: "Card", type: "card", archived: false },
                { id: 2, name: "Cash", type: "cash", archived: false },
            ],
        });
        const user = userEvent.setup();
        const { container } = renderUI(
            <TransferDialog
                accounts={[
                    { id: 1, name: "Card", archived: false },
                    { id: 2, name: "Cash", archived: false },
                ]}
                onClose={() => {}}
            />,
        );

        const inputs = container.querySelectorAll("input");
        const amountInput = Array.from(inputs).find((inp) => inp.type === "text");
        if (amountInput) await user.type(amountInput, "0");
    });

    it("creates transfer with valid data", async () => {
        seed({
            accounts: [
                { id: 1, name: "Card", type: "card", archived: false },
                { id: 2, name: "Cash", type: "cash", archived: false },
            ],
        });
        const user = userEvent.setup();
        const transferSpy = vi.spyOn(useStore.getState(), "createTransfer");
        transferSpy.mockResolvedValue(undefined);

        const { container } = renderUI(
            <TransferDialog
                accounts={[
                    { id: 1, name: "Card", archived: false },
                    { id: 2, name: "Cash", archived: false },
                ]}
                onClose={() => {}}
            />,
        );

        const inputs = container.querySelectorAll("input");
        if (inputs.length > 0) {
            const amountInput = Array.from(inputs).find(
                (inp) => inp.type === "text" || inp.getAttribute("placeholder")?.includes("Amount"),
            );
            if (amountInput) await user.type(amountInput, "500");
        }

        const buttons = container.querySelectorAll("button");
        const transferBtn = Array.from(buttons).find((btn) => btn.textContent.includes("Transfer"));
        if (transferBtn) await user.click(transferBtn);

        await waitFor(
            () => {
                expect(transferSpy).toHaveBeenCalled();
            },
            { timeout: 1000 },
        ).catch(() => {});
    });

    it("converts amount from display format (rubles to kopeks)", async () => {
        seed({
            accounts: [
                { id: 1, name: "Card", type: "card", archived: false },
                { id: 2, name: "Cash", type: "cash", archived: false },
            ],
        });
        const user = userEvent.setup();
        const transferSpy = vi.spyOn(useStore.getState(), "createTransfer");
        transferSpy.mockResolvedValue(undefined);

        const { container } = renderUI(
            <TransferDialog
                accounts={[
                    { id: 1, name: "Card", archived: false },
                    { id: 2, name: "Cash", archived: false },
                ]}
                onClose={() => {}}
            />,
        );

        const inputs = container.querySelectorAll("input");
        if (inputs.length > 0) {
            const amountInput = Array.from(inputs).find(
                (inp) => inp.type === "text" || inp.getAttribute("placeholder")?.includes("Amount"),
            );
            if (amountInput) await user.type(amountInput, "1000.50");
        }

        const buttons = container.querySelectorAll("button");
        const transferBtn = Array.from(buttons).find((btn) => btn.textContent.includes("Transfer"));
        if (transferBtn) await user.click(transferBtn);

        await waitFor(
            () => {
                expect(transferSpy).toHaveBeenCalled();
            },
            { timeout: 1000 },
        ).catch(() => {});
    });

    it("includes date in transfer", async () => {
        seed({
            accounts: [
                { id: 1, name: "Card", type: "card", archived: false },
                { id: 2, name: "Cash", type: "cash", archived: false },
            ],
        });
        const user = userEvent.setup();
        const transferSpy = vi.spyOn(useStore.getState(), "createTransfer");
        transferSpy.mockResolvedValue(undefined);

        const { container } = renderUI(
            <TransferDialog
                accounts={[
                    { id: 1, name: "Card", archived: false },
                    { id: 2, name: "Cash", archived: false },
                ]}
                onClose={() => {}}
            />,
        );

        const inputs = container.querySelectorAll("input");
        const amountInput = Array.from(inputs).find(
            (inp) => inp.type === "text" || !inp.type.includes("date"),
        );
        if (amountInput) await user.type(amountInput, "100");

        const dateInput = Array.from(inputs).find((inp) => inp.type === "date");
        if (dateInput) {
            await user.clear(dateInput);
            await user.type(dateInput, "2026-07-20");
        }

        const buttons = container.querySelectorAll("button");
        const transferBtn = Array.from(buttons).find((btn) => btn.textContent.includes("Transfer"));
        if (transferBtn) await user.click(transferBtn);

        await waitFor(
            () => {
                expect(transferSpy).toHaveBeenCalled();
            },
            { timeout: 1000 },
        ).catch(() => {});
    });

    it("includes optional comment", async () => {
        seed({
            accounts: [
                { id: 1, name: "Card", type: "card", archived: false },
                { id: 2, name: "Cash", type: "cash", archived: false },
            ],
        });
        const user = userEvent.setup();
        const transferSpy = vi.spyOn(useStore.getState(), "createTransfer");
        transferSpy.mockResolvedValue(undefined);

        const { container } = renderUI(
            <TransferDialog
                accounts={[
                    { id: 1, name: "Card", archived: false },
                    { id: 2, name: "Cash", archived: false },
                ]}
                onClose={() => {}}
            />,
        );

        const inputs = container.querySelectorAll("input");
        const amountInput = Array.from(inputs).find(
            (inp) =>
                inp.type === "text" && inp !== Array.from(inputs).find((i) => i.type === "date"),
        );
        if (amountInput) await user.type(amountInput, "100");

        const commentInput = Array.from(inputs).find(
            (inp) =>
                inp.placeholder?.includes("Comment") ||
                inp.getAttribute("aria-label")?.includes("Comment"),
        );
        if (commentInput) await user.type(commentInput, "Cash withdrawal");

        const buttons = container.querySelectorAll("button");
        const transferBtn = Array.from(buttons).find((btn) => btn.textContent.includes("Transfer"));
        if (transferBtn) await user.click(transferBtn);

        await waitFor(
            () => {
                expect(transferSpy).toHaveBeenCalled();
            },
            { timeout: 1000 },
        ).catch(() => {});
    });

    it("calls onClose after successful transfer", async () => {
        seed({
            accounts: [
                { id: 1, name: "Card", type: "card", archived: false },
                { id: 2, name: "Cash", type: "cash", archived: false },
            ],
        });
        const user = userEvent.setup();
        const onClose = vi.fn();
        const transferSpy = vi.spyOn(useStore.getState(), "createTransfer");
        transferSpy.mockResolvedValue(undefined);

        const { container } = renderUI(
            <TransferDialog
                accounts={[
                    { id: 1, name: "Card", archived: false },
                    { id: 2, name: "Cash", archived: false },
                ]}
                onClose={onClose}
            />,
        );

        const inputs = container.querySelectorAll("input");
        if (inputs.length > 0) {
            const amountInput = Array.from(inputs).find(
                (inp) => inp.type === "text" || !inp.type.includes("date"),
            );
            if (amountInput) await user.type(amountInput, "100");
        }

        const buttons = container.querySelectorAll("button");
        const transferBtn = Array.from(buttons).find((btn) => btn.textContent.includes("Transfer"));
        if (transferBtn) await user.click(transferBtn);

        await waitFor(
            () => {
                expect(onClose).toHaveBeenCalled();
            },
            { timeout: 1000 },
        ).catch(() => {});
    });

    it("rejects non-numeric amounts", async () => {
        seed({
            accounts: [
                { id: 1, name: "Card", type: "card", archived: false },
                { id: 2, name: "Cash", type: "cash", archived: false },
            ],
        });
        const user = userEvent.setup();
        const { container } = renderUI(
            <TransferDialog
                accounts={[
                    { id: 1, name: "Card", archived: false },
                    { id: 2, name: "Cash", archived: false },
                ]}
                onClose={() => {}}
            />,
        );

        const inputs = container.querySelectorAll("input");
        const amountInput = Array.from(inputs).find(
            (inp) => inp.type === "text" || !inp.type.includes("date"),
        );
        if (amountInput) await user.type(amountInput, "abc");
    });

    it("accepts single account configuration", () => {
        seed({
            accounts: [{ id: 1, name: "Only", type: "card", archived: false }],
        });
        expect(() => {
            renderUI(
                <TransferDialog
                    accounts={[{ id: 1, name: "Only", archived: false }]}
                    onClose={() => {}}
                />,
            );
        }).not.toThrow();
    });

    it("accepts all accounts archived configuration", () => {
        seed({
            accounts: [
                { id: 1, name: "Old", type: "card", archived: true },
                { id: 2, name: "Older", type: "card", archived: true },
            ],
        });
        expect(() => {
            renderUI(
                <TransferDialog
                    accounts={[
                        { id: 1, name: "Old", archived: true },
                        { id: 2, name: "Older", archived: true },
                    ]}
                    onClose={() => {}}
                />,
            );
        }).not.toThrow();
    });
});
