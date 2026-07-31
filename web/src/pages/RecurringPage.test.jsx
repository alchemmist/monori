import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api.js";
import { renderUI, resetStore, screen, seed, setPath, waitFor } from "../test/render.jsx";
import RecurringPage from "./RecurringPage.jsx";

vi.mock("../api.js");

const schedule = {
    id: 7,
    accountId: 1,
    categoryId: 2,
    payee: "Internet provider",
    description: "Internet",
    amount: -1_500_00,
    frequency: "monthly",
    interval: 1,
    startDate: "2026-01-01",
    nextDate: "2026-08-01",
    endDate: null,
    autoCreate: true,
    active: true,
};

describe("RecurringPage", () => {
    beforeEach(() => {
        resetStore();
        setPath("/");
        seed();
        vi.clearAllMocks();
        api.recurring.mockResolvedValue({ rows: [schedule], createdTransactionIds: [] });
        api.deleteRecurring.mockResolvedValue({ ok: true });
    });

    it("shows recurring transaction details", async () => {
        renderUI(<RecurringPage />);

        expect(await screen.findByText("Internet provider")).toBeInTheDocument();
        expect(screen.getByText("Card · Groceries")).toBeInTheDocument();
        expect(screen.getByText("Next: 2026-08-01")).toBeInTheDocument();
        expect(screen.getByText("automatic")).toBeInTheDocument();
        expect(document.querySelector(".recurring-row__amount")).toHaveTextContent("-1 500 ₽");
    });

    it("deletes a schedule and removes its row", async () => {
        const { user } = renderUI(<RecurringPage />);
        await screen.findByText("Internet provider");

        await user.click(screen.getByRole("button", { name: "Delete Internet provider" }));

        expect(api.deleteRecurring).toHaveBeenCalledWith(7);
        await waitFor(() =>
            expect(screen.queryByText("Internet provider")).not.toBeInTheDocument(),
        );
    });
});
