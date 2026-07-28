import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App from "./App.jsx";
import { api } from "./api.js";
import { renderUI, screen, waitFor, atDemo, setPath, resetStore } from "./test/render.jsx";
import { useStore } from "./store.js";

vi.mock("./api.js");

// the admin page has a data load of its own; App's guard is what is under test
vi.mock("./pages/AdminPage.jsx", () => ({
    default: () => <div data-testid="admin-page">Admin page</div>,
}));

// this Node build ships no localStorage and App reads it on mount
if (!globalThis.localStorage) {
    const data = new Map();
    globalThis.localStorage = {
        getItem: (key) => data.get(key) ?? null,
        setItem: (key, value) => data.set(key, String(value)),
        removeItem: (key) => data.delete(key),
        clear: () => data.clear(),
    };
}

const CURRENT_YEAR = new Date().getFullYear();

/** The app under the demo dataset, already filled — the shell tests want data. */
function renderDemo() {
    atDemo();
    return renderUI(
        <MemoryRouter>
            <App theme="light" onToggleTheme={() => {}} />
        </MemoryRouter>,
    );
}

describe("App", () => {
    beforeEach(() => {
        resetStore();
        localStorage.clear();
        vi.clearAllMocks();
    });

    afterEach(() => {
        setPath("/");
    });

    it("renders the sidebar, the logo and the demo banner once the data is in", async () => {
        const { container } = renderDemo();
        await waitFor(() => expect(container.querySelector(".sidebar")).toBeInTheDocument());
        expect(screen.getByTitle("monori")).toBeInTheDocument();
        expect(screen.getByText("Demo")).toBeInTheDocument();
        expect(screen.getByText(/Sample data/)).toBeInTheDocument();
    });

    it("shows every navigation destination and marks Budget as the landing page", async () => {
        renderDemo();
        const budget = await screen.findByRole("button", { name: "Budget" });
        expect(budget).toHaveClass("sidebar__item_active");
        for (const title of ["Dashboard", "Transactions", "Accounts", "Categories"]) {
            expect(screen.getByRole("button", { name: title })).not.toHaveClass(
                "sidebar__item_active",
            );
        }
    });

    it("switches the content pane when a sidebar destination is clicked", async () => {
        const { user } = renderDemo();
        const budget = await screen.findByRole("button", { name: "Budget" });
        expect(screen.getByRole("heading", { name: "Budget" })).toBeInTheDocument();

        const transactions = screen.getByRole("button", { name: "Transactions" });
        await user.click(transactions);
        await waitFor(() =>
            expect(screen.getByRole("heading", { name: "Transactions" })).toBeInTheDocument(),
        );
        expect(transactions).toHaveClass("sidebar__item_active");
        expect(budget).not.toHaveClass("sidebar__item_active");
        expect(screen.queryByRole("heading", { name: "Budget" })).not.toBeInTheDocument();
    });

    it("offers years up to the one after the latest data or the current year", async () => {
        const { user } = renderDemo();
        await screen.findByRole("heading", { name: "Budget" });
        await user.click(screen.getByRole("button", { name: String(CURRENT_YEAR) }));
        const years = (await screen.findAllByRole("option")).map((o) => o.textContent);
        expect(years[0]).toBe("2020");
        expect(years.at(-1)).toBe(String(CURRENT_YEAR + 1));
    });

    it("shows the roadmap destinations as disabled", async () => {
        renderDemo();
        await screen.findByRole("button", { name: "Budget" });
        const soon = screen.getByText("Net worth").closest(".sidebar__item");
        expect(soon).toHaveAttribute("aria-disabled", "true");
        expect(soon.tagName).toBe("DIV");
    });

    it("links out to the docs and to a pre-filled bug report", async () => {
        renderDemo();
        await screen.findByRole("button", { name: "Budget" });
        expect(screen.getByRole("link", { name: "Docs" })).toHaveAttribute("href", "/docs");
        expect(screen.getByRole("link", { name: "Report a bug" })).toHaveAttribute(
            "href",
            expect.stringContaining("github.com/alchemmist/monori/issues/new?labels=bug"),
        );
    });

    it("collapses the sidebar and remembers the choice", async () => {
        const { container, user } = renderDemo();
        await screen.findByRole("button", { name: "Budget" });
        const sidebar = container.querySelector(".sidebar");
        expect(sidebar).not.toHaveClass("sidebar_collapsed");

        await user.click(screen.getByLabelText("Collapse sidebar"));
        await waitFor(() => expect(sidebar).toHaveClass("sidebar_collapsed"));
        expect(localStorage.getItem("sidebar_collapsed")).toBe("1");

        await user.click(screen.getByLabelText("Expand sidebar"));
        await waitFor(() => expect(sidebar).not.toHaveClass("sidebar_collapsed"));
        expect(localStorage.getItem("sidebar_collapsed")).toBe("0");
    });

    it("replaces the app with a loader while the snapshot is on its way", async () => {
        renderDemo();
        await screen.findByRole("button", { name: "Budget" });
        useStore.setState({ loading: true });
        await waitFor(() =>
            expect(screen.queryByRole("button", { name: "Budget" })).not.toBeInTheDocument(),
        );
    });

    it("replaces the app with the failure message when loading fails", async () => {
        renderDemo();
        await screen.findByRole("button", { name: "Budget" });
        useStore.setState({ error: "Failed to fetch" });
        expect(await screen.findByText("Failed to load data: Failed to fetch")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Budget" })).not.toBeInTheDocument();
    });

    describe("admin", () => {
        /** A signed-in session outside /demo, so the admin guards actually run. */
        async function renderSignedIn(isAdmin) {
            setPath("/");
            localStorage.setItem("monori_token", "t");
            api.authMe.mockResolvedValue({ id: 1, email: "a@example.test", isAdmin });
            api.snapshot.mockResolvedValue({
                accounts: [],
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
                transactionsTotal: 0,
                connections: [],
            });
            const rendered = renderUI(
                <MemoryRouter>
                    <App theme="light" onToggleTheme={() => {}} />
                </MemoryRouter>,
            );
            await screen.findByRole("button", { name: "Budget" });
            return rendered;
        }

        it("opens the admin page for an admin", async () => {
            const { user } = await renderSignedIn(true);
            await user.click(screen.getByRole("button", { name: "Admin" }));
            expect(await screen.findByTestId("admin-page")).toBeInTheDocument();
        });

        it("does not render the admin page once the session loses its admin rights", async () => {
            const { user } = await renderSignedIn(true);
            await user.click(screen.getByRole("button", { name: "Admin" }));
            await screen.findByTestId("admin-page");

            // the render guard next to the link guard: dropping the flag must
            // take the page down, not just the sidebar entry
            useStore.setState({ user: { id: 1, email: "a@example.test", isAdmin: false } });
            await waitFor(() =>
                expect(screen.queryByRole("button", { name: "Admin" })).not.toBeInTheDocument(),
            );
            expect(screen.queryByTestId("admin-page")).not.toBeInTheDocument();
        });

        it("hides the admin link from a non-admin session", async () => {
            await renderSignedIn(false);
            expect(screen.queryByRole("button", { name: "Admin" })).not.toBeInTheDocument();
            expect(screen.getByRole("button", { name: "Settings" })).toBeInTheDocument();
        });
    });
});
