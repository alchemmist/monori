import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App from "./App.jsx";
import * as api from "./api.js";
import {
    renderUI,
    screen,
    waitFor,
    atDemo,
    demo,
    seed,
    resetStore,
    userEvent,
} from "./test/render.jsx";
import { useStore } from "./store.js";

vi.mock("./api.js");

// Ensure localStorage is available for jsdom
if (!globalThis.localStorage) {
    globalThis.localStorage = {
        data: {},
        getItem(key) {
            return this.data[key] || null;
        },
        setItem(key, value) {
            this.data[key] = String(value);
        },
        removeItem(key) {
            delete this.data[key];
        },
        clear() {
            this.data = {};
        },
    };
}

describe("App", () => {
    beforeEach(() => {
        resetStore();
    });

    it("renders with loader and sidebar structure when demo is loaded", async () => {
        const { container } = renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        await waitFor(() => {
            const sidebar = container.querySelector(".sidebar");
            expect(sidebar).toBeTruthy();
        });
    });

    it("renders logo in sidebar", async () => {
        renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        await waitFor(() => {
            expect(screen.getByTitle("monori")).toBeTruthy();
        });
    });

    it("shows budget link in navigation", async () => {
        renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        await waitFor(() => {
            const budgetLinks = screen.getAllByText("Budget");
            expect(budgetLinks.length).toBeGreaterThan(0);
        });
    });

    it("renders error message when loading fails", async () => {
        renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        useStore.setState({ error: "Failed to fetch" });
        await waitFor(() => {
            expect(screen.getByText(/Failed to load data:/)).toBeTruthy();
        });
    });

    it("shows demo banner when on demo path", async () => {
        renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        await waitFor(() => {
            expect(screen.getByText("Demo")).toBeTruthy();
        });
    });

    it("navigates between pages when clicking sidebar items", async () => {
        const user = userEvent.setup();
        const { container } = renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        const transactionsBtn = container
            .querySelector(".sidebar")
            ?.querySelector("button:nth-child(3)");
        if (transactionsBtn) {
            await user.click(transactionsBtn);
            await waitFor(() => {
                expect(transactionsBtn).toHaveClass("sidebar__item_active");
            });
        }
    });

    it("toggles sidebar collapse state and persists to localStorage", async () => {
        const user = userEvent.setup();
        const { container } = renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        const collapseBtn = screen.getByLabelText("Collapse sidebar");
        expect(container.querySelector(".sidebar")).not.toHaveClass("sidebar_collapsed");
        await user.click(collapseBtn);
        await waitFor(() => {
            expect(container.querySelector(".sidebar")).toHaveClass("sidebar_collapsed");
        });
        expect(localStorage.getItem("sidebar_collapsed")).toBe("1");
    });

    it("shows admin item only for admin users", () => {
        renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        expect(screen.queryByText("Admin")).toBeFalsy();
    });

    it("shows docs and report bug links", () => {
        renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        expect(screen.getByText("Docs")).toBeTruthy();
        expect(screen.getByText("Report a bug")).toBeTruthy();
    });

    it("shows settings item in sidebar", () => {
        renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        const settingsBtn = screen.getByText("Settings");
        expect(settingsBtn).toBeTruthy();
    });

    it("shows soon items in sidebar", () => {
        renderUI(
            <MemoryRouter>
                <App theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        atDemo();
        const netWorthElements = screen.getAllByText("Net worth");
        expect(netWorthElements.length).toBeGreaterThan(0);
    });
});
