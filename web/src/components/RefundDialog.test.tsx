import { beforeEach, describe, expect, it, vi } from "vitest";
import RefundDialog from "./RefundDialog.jsx";
import { renderUI, resetStore, screen, seed, tx, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";

const refund = tx(2, { amount: 2400, description: "Shop refund", refundOfId: null });
const purchase = tx(1, { amount: -10000, description: "Shop" });

describe("RefundDialog", () => {
    beforeEach(() => {
        resetStore();
        seed({ transactions: [purchase, refund] });
    });

    it("loads a suggestion, links it and closes", async () => {
        vi.spyOn(useStore.getState(), "refundSuggestions").mockResolvedValue([purchase]);
        const link = vi.spyOn(useStore.getState(), "linkRefund").mockResolvedValue();
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { user } = renderUI(<RefundDialog transaction={refund} onClose={close} />);

        await user.click(screen.getByRole("button", { name: /original purchase/i }));
        await user.click(await screen.findByRole("option", { name: /Shop/ }));
        await user.click(screen.getByRole("button", { name: "Link refund" }));

        await waitFor(() => expect(link).toHaveBeenCalledWith(2, 1));
        expect(notify).toHaveBeenCalledWith({ title: "Refund linked", theme: "success" });
        expect(close).toHaveBeenCalledOnce();
    });

    it("starts with the existing original selected", async () => {
        vi.spyOn(useStore.getState(), "refundSuggestions").mockResolvedValue([purchase]);
        renderUI(<RefundDialog transaction={{ ...refund, refundOfId: 1 }} onClose={vi.fn()} />);
        expect(
            await screen.findByRole("button", { name: /original purchase.*Shop/i }),
        ).toBeInTheDocument();
    });

    it("reports suggestion and link failures", async () => {
        const notify = vi.spyOn(useStore.getState(), "notify");
        vi.spyOn(useStore.getState(), "refundSuggestions").mockRejectedValueOnce(new Error("load"));
        const { unmount } = renderUI(<RefundDialog transaction={refund} onClose={vi.fn()} />);
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({
                    title: "Failed to load refund suggestions",
                }),
            ),
        );
        unmount();

        vi.spyOn(useStore.getState(), "refundSuggestions").mockResolvedValue([purchase]);
        vi.spyOn(useStore.getState(), "linkRefund").mockRejectedValue(new Error("save"));
        const { user } = renderUI(<RefundDialog transaction={refund} onClose={vi.fn()} />);
        await user.click(screen.getByRole("button", { name: /original purchase/i }));
        await user.click(await screen.findByRole("option", { name: /Shop/ }));
        await user.click(screen.getByRole("button", { name: "Link refund" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({
                    title: "Failed to link refund",
                }),
            ),
        );
    });
});
