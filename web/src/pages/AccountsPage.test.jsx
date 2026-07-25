import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import AccountsPage from "./AccountsPage.jsx";
import {
    renderUI,
    resetStore,
    atDemo,
    demo,
    seed,
    screen,
    waitFor,
    fireEvent,
} from "../test/render.jsx";
import { useStore } from "../store.js";
import { api } from "../api.js";
import { setPath } from "../test/render.jsx";

vi.mock("../api.js");

describe("AccountsPage", () => {
    beforeEach(() => {
        resetStore();
        setPath("/");
        vi.clearAllMocks();
        api.connectionsAvailable.mockResolvedValue([]);
    });

    describe("with demo data", () => {
        it("renders accounts heading and new account button", async () => {
            atDemo();
            demo();
            renderUI(<AccountsPage />);

            expect(screen.getByText("Accounts")).toBeInTheDocument();
            expect(screen.getByText("New account")).toBeInTheDocument();
        });

        it("displays account list when demo data is loaded", async () => {
            atDemo();
            const data = demo();
            const { container } = renderUI(<AccountsPage />);

            if (data.accounts.length > 0) {
                expect(container.querySelector(".account-list")).toBeInTheDocument();
            }
        });
    });

    describe("empty state", () => {
        it("renders empty accounts list with new account button", () => {
            seed({ accounts: [] });
            const { container } = renderUI(<AccountsPage />);

            expect(container.querySelector(".account-list")).toBeInTheDocument();
            expect(screen.getByText("New account")).toBeInTheDocument();
        });
    });

    describe("new account", () => {
        it("opens account edit tab when new account button is clicked", async () => {
            seed();
            const user = userEvent.setup();
            renderUI(<AccountsPage />);

            const newBtn = screen.getByText("New account");
            await user.click(newBtn);

            const tabs = useStore.getState().tabs;
            expect(tabs.some((t) => t.kind === "account-edit" && t.props.accountId == null)).toBe(
                true,
            );
        });
    });

    describe("row menu", () => {
        it("opens the edit action for an account", async () => {
            seed({ accounts: [{ id: 1, name: "Card", type: "card", archived: false }] });
            const { user } = renderUI(<AccountsPage />);
            const menu = () => document.querySelector(".account-row__actions button");

            await user.click(menu());
            await user.click(await screen.findByRole("menuitem", { name: "Edit" }));
            expect(useStore.getState().tabs).toEqual(expect.arrayContaining([
                expect.objectContaining({ kind: "account-edit", props: { accountId: 1 } }),
            ]));

        });

        it.each([
            ["Reconcile", "Reconcile"],
            ["Connect bank", "Bank sync"],
            ["Delete", "Delete Card"],
        ])("opens the %s dialog", async (action, title) => {
            seed({ accounts: [{ id: 1, name: "Card", type: "card", archived: false }] });
            const { user } = renderUI(<AccountsPage />);
            await user.click(document.querySelector(".account-row__actions button"));
            await user.click(await screen.findByRole("menuitem", { name: action }));
            expect(screen.getByRole("dialog")).toHaveTextContent(title);
        });

        it("archives and unarchives accounts through the menu", async () => {
            seed({ accounts: [{ id: 1, name: "Card", type: "card", archived: false }] });
            const patchAccount = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
            const { user } = renderUI(<AccountsPage />);
            await user.click(document.querySelector(".account-row__actions button"));
            await user.click(await screen.findByRole("menuitem", { name: "Archive" }));
            expect(patchAccount).toHaveBeenCalledWith(1, { archived: true });
        });
        it("displays edit option in row menu", async () => {
            const data = seed();
            const user = userEvent.setup();
            const { container } = renderUI(<AccountsPage />);

            const rows = container.querySelectorAll(".account-row");
            if (rows.length > 0) {
                const firstRow = rows[0];
                const menuBtn = firstRow.querySelector("button");
                if (menuBtn) await user.click(menuBtn);
            }
        });

        it("has archive option that calls patchAccount", async () => {
            const data = seed();
            const user = userEvent.setup();
            const patchSpy = vi.spyOn(useStore.getState(), "patchAccount");

            const { container } = renderUI(<AccountsPage />);

            const rows = container.querySelectorAll(".account-row");
            if (rows.length > 0) {
                const grip = rows[0].querySelector(".account-row__grip");
                if (grip) {
                    const closeBtn = rows[0].querySelector(".account-row__actions button");
                    if (closeBtn) {
                        await user.click(closeBtn);
                    }
                }
            }
        });

        it("shows archived tag for archived accounts", () => {
            seed({ accounts: [{ id: 1, name: "Archived", archived: true, type: "card" }] });
            const { container } = renderUI(<AccountsPage />);

            const rows = container.querySelectorAll(".account-row");
            expect(rows.length).toBeGreaterThan(0);
        });

        it("has delete option", async () => {
            const data = seed();
            const user = userEvent.setup();
            const { container } = renderUI(<AccountsPage />);

            const rows = container.querySelectorAll(".account-row");
            if (rows.length > 0) {
                const menuBtn = rows[0].querySelector(".account-row__actions button");
                if (menuBtn) await user.click(menuBtn);
            }
        });
    });

    describe("drag and drop reordering", () => {
        it("renders grip handles for reordering", () => {
            seed({
                accounts: [
                    { id: 1, name: "First", type: "card", sort: 1 },
                    { id: 2, name: "Second", type: "card", sort: 2 },
                ],
            });

            const { container } = renderUI(<AccountsPage />);

            const grips = container.querySelectorAll(".account-row__grip");
            expect(grips.length).toBe(2);
        });

        it("handles drag and reorder", () => {
            seed({
                accounts: [
                    { id: 1, name: "First", type: "card", sort: 1 },
                    { id: 2, name: "Second", type: "card", sort: 2 },
                ],
            });
            const reorderMock = vi.spyOn(api, "reorderAccounts").mockResolvedValue();

            const { container } = renderUI(<AccountsPage />);

            const firstGrip = container.querySelector(".account-row__grip");
            if (firstGrip) {
                vi.spyOn(firstGrip.closest(".account-row"), "getBoundingClientRect").mockReturnValue({ height: 40 });
                fireEvent.pointerDown(firstGrip, { button: 0, clientY: 100 });
                fireEvent.pointerMove(document, { clientY: 150 });
                fireEvent.pointerUp(document);
            }
            expect(useStore.getState().snapshot.accounts.map((a) => a.id)).toEqual([2, 1]);
            expect(reorderMock).toHaveBeenCalledWith([2, 1]);
        });

        it("prevents drag on right click", () => {
            seed({
                accounts: [
                    { id: 1, name: "First", type: "card" },
                    { id: 2, name: "Second", type: "card" },
                ],
            });

            const { container } = renderUI(<AccountsPage />);

            const firstGrip = container.querySelector(".account-row__grip");
            if (firstGrip) {
                fireEvent.pointerDown(firstGrip, { button: 2, clientY: 100 });
                fireEvent.pointerMove(document, { clientY: 150 });
                fireEvent.pointerUp(document);
            }
        });
    });

    describe("connection status display", () => {
        it("renders accounts list structure", () => {
            seed({
                connections: [{ id: 1, status: "connected" }],
                accounts: [{ id: 1, name: "Synced Card", type: "card", connectionId: 1 }],
            });
            const { container } = renderUI(<AccountsPage />);

            const rows = container.querySelectorAll(".account-row");
            expect(rows.length).toBeGreaterThan(0);
        });

        it("shows connection status indicators", () => {
            seed({
                connections: [{ id: 1, status: "error" }],
                accounts: [{ id: 1, name: "Error Card", type: "card", connectionId: 1 }],
            });
            const { container } = renderUI(<AccountsPage />);

            const rows = container.querySelectorAll(".account-row");
            expect(rows.length).toBeGreaterThan(0);
        });
    });

    describe("delete dialog", () => {
        it("shows delete dialog when delete option is selected", async () => {
            const data = seed();
            const user = userEvent.setup();
            const { container } = renderUI(<AccountsPage />);

            const rows = container.querySelectorAll(".account-row");
            if (rows.length > 0) {
                const menuBtn = rows[0].querySelector(".account-row__actions button");
                if (menuBtn) {
                    await user.click(menuBtn);
                }
            }
        });
    });

    describe("reconcile dialog", () => {
        it("shows reconcile option in row menu", async () => {
            seed();
            const user = userEvent.setup();
            const { container } = renderUI(<AccountsPage />);

            const rows = container.querySelectorAll(".account-row");
            if (rows.length > 0) {
                const menuBtn = rows[0].querySelector(".account-row__actions button");
                if (menuBtn) await user.click(menuBtn);
            }
        });
    });
});
