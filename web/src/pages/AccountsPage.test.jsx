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
        expect(document.querySelectorAll(".account-row:not(.account-row_add)")).toHaveLength(
            data.accounts.length,
        );
    });

    it("renders no rows and still offers a new account when there are none", () => {
        seed({ accounts: [] });
        renderUI(<AccountsPage />);

        expect(document.querySelectorAll(".account-row:not(.account-row_add)")).toHaveLength(0);
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

        it("does nothing when the drag ends on the same row it began", () => {
            twoAccounts();
            const reorder = vi.spyOn(api, "reorderAccounts").mockResolvedValue();
            const { container } = renderUI(<AccountsPage />);

            const grip = container.querySelector(".account-row__grip");
            vi.spyOn(grip.closest(".account-row"), "getBoundingClientRect").mockReturnValue({
                height: 40,
            });
            fireEvent.pointerDown(grip, { button: 0, clientY: 100 });
            // half a row of travel rounds to the same index -> no move
            fireEvent.pointerMove(document, { clientY: 115 });
            fireEvent.pointerUp(document);

            expect(useStore.getState().snapshot.accounts.map((a) => a.id)).toEqual([1, 2]);
            expect(reorder).not.toHaveBeenCalled();
        });

        it("clamps the target to the last row when dragged far past the end", () => {
            twoAccounts();
            const reorder = vi.spyOn(api, "reorderAccounts").mockResolvedValue();
            const { container } = renderUI(<AccountsPage />);

            const grip = container.querySelector(".account-row__grip");
            vi.spyOn(grip.closest(".account-row"), "getBoundingClientRect").mockReturnValue({
                height: 40,
            });
            fireEvent.pointerDown(grip, { button: 0, clientY: 100 });
            // 10 rows of travel, only 2 rows exist -> clamped to index 1
            fireEvent.pointerMove(document, { clientY: 500 });
            fireEvent.pointerUp(document);

            expect(reorder).toHaveBeenCalledWith([2, 1]);
        });

        it("moves a middle account to the end, keeping the others in order", () => {
            seed({
                accounts: [
                    account(1, { name: "First" }),
                    account(2, { name: "Second" }),
                    account(3, { name: "Third" }),
                ],
            });
            const reorder = vi.spyOn(api, "reorderAccounts").mockResolvedValue();
            renderUI(<AccountsPage />);

            const grip = row("Second").querySelector(".account-row__grip");
            vi.spyOn(grip.closest(".account-row"), "getBoundingClientRect").mockReturnValue({
                height: 40,
            });
            fireEvent.pointerDown(grip, { button: 0, clientY: 100 });
            fireEvent.pointerMove(document, { clientY: 140 });
            fireEvent.pointerUp(document);

            expect(reorder).toHaveBeenCalledWith([1, 3, 2]);
            expect(useStore.getState().snapshot.accounts.map((a) => a.id)).toEqual([1, 3, 2]);
        });

        it("marks only the dragged row and lifts it, shifting the others out of the way", () => {
            seed({
                accounts: [
                    account(1, { name: "First" }),
                    account(2, { name: "Second" }),
                    account(3, { name: "Third" }),
                ],
            });
            renderUI(<AccountsPage />);

            const grip = row("First").querySelector(".account-row__grip");
            vi.spyOn(grip.closest(".account-row"), "getBoundingClientRect").mockReturnValue({
                height: 40,
            });
            fireEvent.pointerDown(grip, { button: 0, clientY: 100 });
            fireEvent.pointerMove(document, { clientY: 140 });

            const first = row("First");
            const second = row("Second");
            const third = row("Third");
            expect(first).toHaveClass("account-row_dragging");
            expect(second).not.toHaveClass("account-row_dragging");
            expect(third).not.toHaveClass("account-row_dragging");

            expect(first.style.transform).toBe("translateY(40px)");
            expect(first.style.zIndex).toBe("2");
            expect(first.style.transition).toBe("none");
            // one row of travel: only the passed-over row shifts up, the untouched one stays put
            expect(second.style.transform).toBe("translateY(-40px)");
            expect(third.style.transform).toBe("translateY(0px)");

            fireEvent.pointerUp(document);
        });

        it("clamps the lifted row's own transform to the list bounds", () => {
            twoAccounts();
            renderUI(<AccountsPage />);

            const grip = row("First").querySelector(".account-row__grip");
            vi.spyOn(grip.closest(".account-row"), "getBoundingClientRect").mockReturnValue({
                height: 40,
            });
            fireEvent.pointerDown(grip, { button: 0, clientY: 100 });
            // dragging the first row upward past the top clamps its transform at 0
            fireEvent.pointerMove(document, { clientY: 20 });
            expect(row("First").style.transform).toBe("translateY(0px)");

            fireEvent.pointerUp(document);
        });

        const threeAccounts = () =>
            seed({
                accounts: [
                    account(1, { name: "First" }),
                    account(2, { name: "Second" }),
                    account(3, { name: "Third" }),
                ],
            });

        const startDrag = (name) => {
            const grip = row(name).querySelector(".account-row__grip");
            vi.spyOn(grip.closest(".account-row"), "getBoundingClientRect").mockReturnValue({
                height: 40,
            });
            fireEvent.pointerDown(grip, { button: 0, clientY: 100 });
            return grip;
        };

        it("shifts the passed-over rows down when a lower row is dragged up", () => {
            threeAccounts();
            renderUI(<AccountsPage />);

            startDrag("Third");
            // drag the last row up two rows onto the first row's slot
            fireEvent.pointerMove(document, { clientY: 20 });

            const first = row("First");
            const second = row("Second");
            const third = row("Third");
            expect(third).toHaveClass("account-row_dragging");
            expect(first).not.toHaveClass("account-row_dragging");
            // the two rows it passes (indices 0 and 1, both >= target 0 and < from 2) shift down
            expect(first.style.transform).toBe("translateY(40px)");
            expect(second.style.transform).toBe("translateY(40px)");
            expect(third.style.transform).toBe("translateY(-80px)");
            expect(third.style.zIndex).toBe("2");
            expect(third.style.transition).toBe("none");

            fireEvent.pointerUp(document);
        });

        it("shifts exactly the rows between source and target when dragging one row up", () => {
            threeAccounts();
            renderUI(<AccountsPage />);

            startDrag("Third");
            // drag the last row up a single row: only the middle row is passed over
            fireEvent.pointerMove(document, { clientY: 60 });

            expect(row("First").style.transform).toBe("translateY(0px)");
            expect(row("Second").style.transform).toBe("translateY(40px)");
            expect(row("Third").style.transform).toBe("translateY(-40px)");

            fireEvent.pointerUp(document);
        });

        it("shifts only the rows up to the target when a middle row is dragged down", () => {
            threeAccounts();
            renderUI(<AccountsPage />);

            startDrag("First");
            // drag the first row down a single row onto the middle slot
            fireEvent.pointerMove(document, { clientY: 140 });

            // only the second row (i > 0 and i <= 1) shifts up; the third stays put
            expect(row("First").style.transform).toBe("translateY(40px)");
            expect(row("Second").style.transform).toBe("translateY(-40px)");
            expect(row("Third").style.transform).toBe("translateY(0px)");

            fireEvent.pointerUp(document);
        });

        it("clamps a lower dragged row's own transform to the bottom bound", () => {
            threeAccounts();
            renderUI(<AccountsPage />);

            startDrag("Second");
            // drag the middle row far past the end: its own transform clamps at one row
            fireEvent.pointerMove(document, { clientY: 900 });
            expect(row("Second").style.transform).toBe("translateY(40px)");

            fireEvent.pointerUp(document);
        });

        it("clamps a lower dragged row's own transform to the top bound", () => {
            threeAccounts();
            renderUI(<AccountsPage />);

            startDrag("Second");
            // drag the middle row far past the top: its own transform clamps at minus one row
            fireEvent.pointerMove(document, { clientY: -900 });
            expect(row("Second").style.transform).toBe("translateY(-40px)");

            fireEvent.pointerUp(document);
        });

        it("gives rows no inline transform before any drag starts", () => {
            twoAccounts();
            renderUI(<AccountsPage />);

            expect(row("First").style.transform).toBe("");
            expect(row("Second").style.transform).toBe("");
            expect(row("First")).not.toHaveClass("account-row_dragging");
        });

        it("locks and restores text selection around the drag", () => {
            twoAccounts();
            vi.spyOn(api, "reorderAccounts").mockResolvedValue();
            const { container } = renderUI(<AccountsPage />);

            const grip = container.querySelector(".account-row__grip");
            vi.spyOn(grip.closest(".account-row"), "getBoundingClientRect").mockReturnValue({
                height: 40,
            });
            fireEvent.pointerDown(grip, { button: 0, clientY: 100 });
            expect(document.body.style.userSelect).toBe("none");

            fireEvent.pointerMove(document, { clientY: 150 });
            fireEvent.pointerUp(document);
            expect(document.body.style.userSelect).toBe("");
        });
    });

    describe("more coverage", () => {
        it("passes the computed balance into the reconcile dialog", async () => {
            seed({
                accounts: [account(1, { name: "Card", openingBalance: 1_000_00 })],
                transactions: [
                    { id: 1, accountId: 1, categoryId: 2, amount: -300_00, date: "2026-03-01" },
                ],
            });
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            await user.click(await screen.findByRole("menuitem", { name: "Reconcile" }));

            const dialog = screen.getByRole("dialog");
            expect(dialog).toHaveTextContent("Computed balance");
            expect(dialog.querySelector(".num").textContent).toBe("700 ₽");
        });

        it("reconcile dialog shows a zero balance for an account with no data", async () => {
            seed({ accounts: [account(9, { name: "Empty", openingBalance: 0 })] });
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Empty");
            await user.click(await screen.findByRole("menuitem", { name: "Reconcile" }));

            expect(screen.getByRole("dialog").querySelector(".num").textContent).toBe("0 ₽");
        });

        it("reports zero transactions in the delete dialog for an untouched account", async () => {
            seed({
                accounts: [account(1, { name: "Card" }), account(2, { name: "Cash" })],
                transactions: [
                    { id: 1, accountId: 2, categoryId: 2, amount: -100, date: "2026-03-01" },
                ],
            });
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            await user.click(await screen.findByRole("menuitem", { name: "Delete" }));

            expect(screen.getByRole("dialog")).toHaveTextContent(
                "No transactions belong to this account.",
            );
        });

        it("shows no connection tag for a dangling connection id", () => {
            seed({
                connections: [{ id: 1, status: "connected" }],
                accounts: [account(1, { name: "Orphan", connectionId: 99 })],
            });
            renderUI(<AccountsPage />);

            expect(row("Orphan").querySelectorAll(".tag")).toHaveLength(1);
            expect(row("Orphan").querySelector(".account-row__main")).not.toHaveTextContent(
                "synced",
            );
        });

        it("shows no connection tag when the account has no connection id", () => {
            seed({
                connections: [{ id: 1, status: "connected" }],
                accounts: [account(1, { name: "Manual" })],
            });
            renderUI(<AccountsPage />);

            expect(row("Manual").querySelectorAll(".tag")).toHaveLength(1);
        });

        it("falls back to the raw type when it has no friendly label", () => {
            seed({ accounts: [account(1, { name: "Odd", type: "crypto" })] });
            renderUI(<AccountsPage />);

            expect([...row("Odd").querySelectorAll(".tag")].map((t) => t.textContent)).toEqual([
                "crypto",
            ]);
        });

        it("labels each known account type", () => {
            seed({
                accounts: [
                    account(1, { name: "C", type: "card" }),
                    account(2, { name: "M", type: "cash" }),
                    account(3, { name: "S", type: "savings" }),
                    account(4, { name: "O", type: "other" }),
                ],
            });
            renderUI(<AccountsPage />);

            const typeTag = (name) => row(name).querySelector(".tag").textContent;
            expect(typeTag("C")).toBe("Card");
            expect(typeTag("M")).toBe("Cash");
            expect(typeTag("S")).toBe("Savings");
            expect(typeTag("O")).toBe("Other");
        });

        it("renders the account badge at the row size", () => {
            seed({ accounts: [account(1, { name: "Card" })] });
            renderUI(<AccountsPage />);

            const badge = row("Card").querySelector(".acct-badge");
            expect(badge.style.width).toBe("32px");
            expect(badge.style.height).toBe("32px");
        });

        it("opens the account editor with a stable per-account tab key", async () => {
            seed({ accounts: [account(7, { name: "Card" })] });
            const openTab = vi.spyOn(useStore.getState(), "openTab");
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            await user.click(await screen.findByRole("menuitem", { name: "Edit" }));

            expect(openTab).toHaveBeenCalledWith(
                "account-edit",
                { accountId: 7 },
                "account-edit:7",
            );
        });

        it("hands the existing connection to the connection dialog", async () => {
            seed({
                connections: [{ id: 1, status: "connected", lastSync: null }],
                accounts: [account(1, { name: "Card", connectionId: 1 })],
            });
            const { user } = renderUI(<AccountsPage />);

            await openMenu(user, "Card");
            await user.click(await screen.findByRole("menuitem", { name: "Bank sync" }));

            // with a real connection the dialog opens on the ready step, not credentials
            const dialog = await screen.findByRole("dialog");
            expect(dialog).toHaveTextContent("Last sync");
            expect(dialog).not.toHaveTextContent("Connect & sync");
        });

        it("opens a new blank account tab with its own key", async () => {
            seed({ accounts: [account(1, { name: "Card" })] });
            const openTab = vi.spyOn(useStore.getState(), "openTab");
            const { user } = renderUI(<AccountsPage />);

            await user.click(screen.getByRole("button", { name: /New account/ }));

            expect(openTab).toHaveBeenCalledWith("account-edit", {}, "account-new");
        });
    });
});
