import { beforeEach, describe, expect, it, vi } from "vitest";
import AccountsPage from "./AccountsPage.jsx";
import {
    atDemo,
    demo,
    fireEvent,
    renderUI,
    resetStore,
    screen,
    seed,
    setPath,
} from "../test/render.jsx";
import { useStore } from "../store.js";
import { api } from "../api.js";

vi.mock("../api.js");

const account = (id, patch = {}) => ({
    id,
    name: `Account ${id}`,
    type: "card",
    icon: "card",
    color: "#000",
    openingBalance: 0,
    archived: false,
    ...patch,
});

// account names collide with the type tags ("Card"), so match on the name node
const row = (name) =>
    [...document.querySelectorAll(".account-row")].find(
        (r) => r.querySelector(".account-row__name").textContent === name,
    );
const openMenu = async (user, name) => {
    await user.click(row(name).querySelector(".account-row__actions button"));
};

describe("AccountsPage", () => {
    beforeEach(() => {
        resetStore();
        setPath("/");
        vi.clearAllMocks();
        api.connectionsAvailable.mockResolvedValue([]);
    });

    it("lists the demo accounts under the page heading", () => {
        atDemo();
        const data = demo();
        renderUI(<AccountsPage />);

        expect(screen.getByRole("heading", { name: "Accounts" })).toBeInTheDocument();
        expect(document.querySelectorAll(".account-row")).toHaveLength(data.accounts.length);
    });

    it("renders no rows and still offers a new account when there are none", () => {
        seed({ accounts: [] });
        renderUI(<AccountsPage />);

        expect(document.querySelectorAll(".account-row")).toHaveLength(0);
        expect(screen.getByRole("button", { name: /New account/ })).toBeInTheDocument();
    });

    it("opens a blank account editor from the New account button", async () => {
        seed();
        const { user } = renderUI(<AccountsPage />);

        await user.click(screen.getByRole("button", { name: /New account/ }));

        expect(useStore.getState().tabs).toEqual(
            expect.arrayContaining([expect.objectContaining({ kind: "account-edit", props: {} })]),
        );
    });

    describe("balances", () => {
        it("adds each account's transactions to its opening balance", () => {
            seed({
                accounts: [
                    account(1, { name: "Card", openingBalance: 1_000_00 }),
                    account(2, { name: "Cash", openingBalance: 500_00 }),
                ],
                transactions: [
                    { id: 1, accountId: 1, categoryId: 2, amount: -250_00, date: "2026-03-01" },
                    { id: 2, accountId: 1, categoryId: 1, amount: 100_00, date: "2026-03-02" },
                    { id: 3, accountId: 2, categoryId: 2, amount: -900_00, date: "2026-03-03" },
                ],
            });
            renderUI(<AccountsPage />);

            const balance = (name) => row(name).querySelector(".account-row__balance").textContent;
            expect(balance("Card")).toBe("850 ₽");
            expect(balance("Cash")).toBe("-400 ₽");
        });
    });

    describe("tags", () => {
        it("labels an account by type and marks archived ones", () => {
            seed({
                accounts: [
                    account(1, { name: "Everyday", type: "card" }),
                    account(2, { name: "Rainy day", type: "savings", archived: true }),
                ],
            });
            renderUI(<AccountsPage />);

            const tags = (name) =>
                [...row(name).querySelectorAll(".tag")].map((t) => t.textContent);
            expect(tags("Everyday")).toEqual(["Card"]);
            expect(tags("Rainy day")).toEqual(["Savings", "archived"]);
        });

        it("only calls a connection synced when it really is connected", () => {
            seed({
                connections: [
                    { id: 1, status: "connected" },
                    { id: 2, status: "error" },
                    { id: 3, status: "pending" },
                ],
                accounts: [
                    account(1, { name: "Working", connectionId: 1 }),
                    account(2, { name: "Broken", connectionId: 2 }),
                    account(3, { name: "Waiting", connectionId: 3 }),
                    account(4, { name: "Manual" }),
                ],
            });
            renderUI(<AccountsPage />);

            const connTag = (name) => row(name).querySelectorAll(".tag")[1];
            expect(connTag("Working")).toHaveTextContent("synced");
            expect(connTag("Working")).toHaveClass("tag_success");
            expect(connTag("Broken")).toHaveTextContent("error");
            expect(connTag("Broken")).toHaveClass("tag_danger");
            expect(connTag("Waiting")).toHaveTextContent("pending");
            expect(connTag("Waiting")).toHaveClass("tag_info");
            expect(connTag("Manual")).toBeUndefined();
        });
    });

    describe("row menu", () => {
        it("opens the account editor for the row", async () => {
            seed({ accounts: [account(1, { name: "Card" })] });
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            await user.click(await screen.findByRole("menuitem", { name: "Edit" }));

            expect(useStore.getState().tabs).toEqual(
                expect.arrayContaining([
                    expect.objectContaining({ kind: "account-edit", props: { accountId: 1 } }),
                ]),
            );
        });

        it.each([
            ["Reconcile", "Reconcile"],
            ["Connect bank", "Bank sync"],
            ["Delete", "Delete Card"],
        ])("opens the %s dialog", async (action, title) => {
            seed({ accounts: [account(1, { name: "Card" })] });
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            await user.click(await screen.findByRole("menuitem", { name: action }));

            expect(screen.getByRole("dialog")).toHaveTextContent(title);
        });

        it("names the connection action after whether one already exists", async () => {
            seed({
                connections: [{ id: 1, status: "connected" }],
                accounts: [account(1, { name: "Card", connectionId: 1 })],
            });
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            expect(await screen.findByRole("menuitem", { name: "Bank sync" })).toBeInTheDocument();
            expect(
                screen.queryByRole("menuitem", { name: "Connect bank" }),
            ).not.toBeInTheDocument();
        });

        it("archives an account through the menu", async () => {
            seed({ accounts: [account(1, { name: "Card" })] });
            const patchAccount = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            await user.click(await screen.findByRole("menuitem", { name: "Archive" }));

            expect(patchAccount).toHaveBeenCalledWith(1, { archived: true });
        });

        it("unarchives an already archived account", async () => {
            seed({ accounts: [account(1, { name: "Card", archived: true })] });
            const patchAccount = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            await user.click(await screen.findByRole("menuitem", { name: "Unarchive" }));

            expect(patchAccount).toHaveBeenCalledWith(1, { archived: false });
        });

        it("warns when archiving fails instead of failing silently", async () => {
            seed({ accounts: [account(1, { name: "Card" })] });
            vi.spyOn(useStore.getState(), "patchAccount").mockRejectedValue(new Error("offline"));
            const notify = vi.spyOn(useStore.getState(), "notify");
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            await user.click(await screen.findByRole("menuitem", { name: "Archive" }));

            await vi.waitFor(() =>
                expect(notify).toHaveBeenCalledWith(
                    expect.objectContaining({
                        title: "Failed to update account",
                        theme: "danger",
                    }),
                ),
            );
        });

        it("counts the account's transactions into the delete dialog", async () => {
            seed({
                accounts: [account(1, { name: "Card" }), account(2, { name: "Cash" })],
                transactions: [
                    { id: 1, accountId: 1, categoryId: 2, amount: -100, date: "2026-03-01" },
                    { id: 2, accountId: 1, categoryId: 2, amount: -100, date: "2026-03-02" },
                    { id: 3, accountId: 2, categoryId: 2, amount: -100, date: "2026-03-03" },
                ],
            });
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            await user.click(await screen.findByRole("menuitem", { name: "Delete" }));

            expect(screen.getByRole("dialog")).toHaveTextContent("2");
        });
    });

    describe("drag and drop reordering", () => {
        const twoAccounts = () =>
            seed({
                accounts: [account(1, { name: "First" }), account(2, { name: "Second" })],
            });

        const dragFirstDown = (container) => {
            const grip = container.querySelector(".account-row__grip");
            vi.spyOn(grip.closest(".account-row"), "getBoundingClientRect").mockReturnValue({
                height: 40,
            });
            fireEvent.pointerDown(grip, { button: 0, clientY: 100 });
            fireEvent.pointerMove(document, { clientY: 150 });
            fireEvent.pointerUp(document);
        };

        it("gives every row a grip", () => {
            twoAccounts();
            const { container } = renderUI(<AccountsPage />);

            expect(container.querySelectorAll(".account-row__grip")).toHaveLength(2);
        });

        it("reorders the accounts and persists the new order", () => {
            twoAccounts();
            const reorder = vi.spyOn(api, "reorderAccounts").mockResolvedValue();
            const { container } = renderUI(<AccountsPage />);

            dragFirstDown(container);

            expect(useStore.getState().snapshot.accounts.map((a) => a.id)).toEqual([2, 1]);
            expect(reorder).toHaveBeenCalledWith([2, 1]);
        });

        it("leaves the order alone when a right click starts on the grip", () => {
            twoAccounts();
            const reorder = vi.spyOn(api, "reorderAccounts").mockResolvedValue();
            const { container } = renderUI(<AccountsPage />);

            const grip = container.querySelector(".account-row__grip");
            fireEvent.pointerDown(grip, { button: 2, clientY: 100 });
            fireEvent.pointerMove(document, { clientY: 150 });
            fireEvent.pointerUp(document);

            expect(useStore.getState().snapshot.accounts.map((a) => a.id)).toEqual([1, 2]);
            expect(reorder).not.toHaveBeenCalled();
        });

        it("keeps the reorder local while on the demo", () => {
            atDemo();
            twoAccounts();
            const reorder = vi.spyOn(api, "reorderAccounts").mockResolvedValue();
            const { container } = renderUI(<AccountsPage />);

            dragFirstDown(container);

            expect(useStore.getState().snapshot.accounts.map((a) => a.id)).toEqual([2, 1]);
            expect(reorder).not.toHaveBeenCalled();
        });
    });
});
