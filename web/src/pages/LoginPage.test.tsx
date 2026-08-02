import { describe, expect, it, vi, afterEach } from "vitest";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import LoginPage from "./LoginPage.jsx";
import { fireEvent, renderUI, screen, waitFor, resetStore } from "../test/render.jsx";

vi.mock("../api.js");

type LoginEntry = string | { pathname: string; state?: unknown };

function LocationProbe() {
    const location = useLocation();
    const navigate = useNavigate();
    return (
        <div>
            <span data-testid="current-location">
                {location.pathname}
                {location.search}
                {location.hash}
            </span>
            <button type="button" onClick={() => void navigate(-1)}>
                Back in test history
            </button>
        </div>
    );
}

function renderLogin(initialEntries: LoginEntry[] = ["/login"], initialIndex?: number) {
    return renderUI(
        <MemoryRouter
            initialEntries={initialEntries}
            {...(initialIndex === undefined ? {} : { initialIndex })}
        >
            <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="*" element={<LocationProbe />} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("LoginPage", () => {
    afterEach(() => {
        vi.restoreAllMocks();
        resetStore();
    });
    it("renders the login form with email and password fields", () => {
        renderLogin();
        expect(screen.getByPlaceholderText("Email")).toBeInTheDocument();
        expect(screen.getByPlaceholderText("Password")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    });

    it("starts in login mode with 'Every ruble in its place' title", () => {
        renderLogin();
        expect(screen.getByText(/Every ruble/, { exact: false })).toBeInTheDocument();
    });

    it("switches to register mode when Register is clicked", async () => {
        const { user } = renderLogin();
        const switchButton = screen.getByRole("button", { name: "Register" });
        await user.click(switchButton);
        expect(screen.getByText(/Start counting/, { exact: false })).toBeInTheDocument();
        expect(screen.getByPlaceholderText("Password (min 8 characters)")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
    });

    it("switches back to login mode when Sign in is clicked from register", async () => {
        const { user } = renderLogin();
        await user.click(screen.getByRole("button", { name: "Register" }));
        await user.click(screen.getByRole("button", { name: "Sign in" }));
        expect(screen.getByText(/Every ruble/, { exact: false })).toBeInTheDocument();
        expect(screen.getByPlaceholderText("Password")).toBeInTheDocument();
    });

    it("toggles password visibility with eye button", async () => {
        const { user } = renderLogin();
        const passwordInput = screen.getByPlaceholderText("Password");
        const eyeButton = screen.getByRole("button", { name: "Show password" });
        expect(passwordInput).toHaveAttribute("type", "password");
        await user.click(eyeButton);
        expect(passwordInput).toHaveAttribute("type", "text");
        await user.click(eyeButton);
        expect(passwordInput).toHaveAttribute("type", "password");
    });

    it("disables submit button while request is in flight", async () => {
        const { user } = renderLogin();
        const submitButton = screen.getByRole("button", { name: "Sign in" });
        const emailInput = screen.getByPlaceholderText("Email");
        const passwordInput = screen.getByPlaceholderText("Password");

        const { useStore } = await import("../store.js");
        let resolveLogin = () => {};
        vi.spyOn(useStore.getState(), "login").mockImplementation(
            () =>
                new Promise((resolve) => {
                    resolveLogin = resolve;
                }),
        );

        await user.type(emailInput, "user@example.com");
        await user.type(passwordInput, "password");

        await user.click(submitButton);
        expect(submitButton).toBeDisabled();

        resolveLogin();
    });

    it("displays error message on login failure with email field highlighting", async () => {
        const { user } = renderLogin();
        const { useStore } = await import("../store.js");
        const loginSpy = vi
            .spyOn(useStore.getState(), "login")
            .mockRejectedValueOnce(new Error("Invalid email"));

        const emailInput = screen.getByPlaceholderText("Email");
        const passwordInput = screen.getByPlaceholderText("Password");
        const submitButton = screen.getByRole("button", { name: "Sign in" });

        await user.type(emailInput, "invalid@test.com");
        await user.type(passwordInput, "wrong");
        await user.click(submitButton);

        await waitFor(() => {
            expect(screen.getByText("Invalid email")).toBeInTheDocument();
        });

        expect(emailInput).toHaveAttribute("aria-invalid");

        loginSpy.mockRestore();
    });

    it("displays error message on login failure with password field highlighting", async () => {
        const { user } = renderLogin();
        const { useStore } = await import("../store.js");
        const loginSpy = vi
            .spyOn(useStore.getState(), "login")
            .mockRejectedValueOnce(new Error("Wrong password"));

        const emailInput = screen.getByPlaceholderText("Email");
        const passwordInput = screen.getByPlaceholderText("Password");
        const submitButton = screen.getByRole("button", { name: "Sign in" });

        await user.type(emailInput, "user@test.com");
        await user.type(passwordInput, "wrong");
        await user.click(submitButton);

        await waitFor(() => {
            expect(screen.getByText("Wrong password")).toBeInTheDocument();
        });

        expect(passwordInput).toHaveAttribute("aria-invalid");

        loginSpy.mockRestore();
    });

    it("displays generic error when message doesn't mention email or password", async () => {
        const { user } = renderLogin();
        const { useStore } = await import("../store.js");
        const loginSpy = vi
            .spyOn(useStore.getState(), "login")
            .mockRejectedValueOnce(new Error("Server error"));

        const emailInput = screen.getByPlaceholderText("Email");
        const passwordInput = screen.getByPlaceholderText("Password");
        const submitButton = screen.getByRole("button", { name: "Sign in" });

        await user.type(emailInput, "user@test.com");
        await user.type(passwordInput, "password");
        await user.click(submitButton);

        await waitFor(() => {
            expect(screen.getByText("Server error")).toBeInTheDocument();
        });

        expect(emailInput).not.toHaveAttribute("aria-invalid");
        expect(passwordInput).not.toHaveAttribute("aria-invalid");

        loginSpy.mockRestore();
    });

    it("clears error message when switching modes", async () => {
        const { user } = renderLogin();
        const { useStore } = await import("../store.js");
        const loginSpy = vi
            .spyOn(useStore.getState(), "login")
            .mockRejectedValueOnce(new Error("Invalid email"));

        const emailInput = screen.getByPlaceholderText("Email");
        const passwordInput = screen.getByPlaceholderText("Password");
        const submitButton = screen.getByRole("button", { name: "Sign in" });

        await user.type(emailInput, "invalid@test.com");
        await user.type(passwordInput, "wrong");
        await user.click(submitButton);

        await waitFor(() => {
            expect(screen.getByText("Invalid email")).toBeInTheDocument();
        });

        await user.click(screen.getByRole("button", { name: "Register" }));
        expect(screen.queryByText("Invalid email")).not.toBeInTheDocument();

        loginSpy.mockRestore();
    });

    it("calls register on registration form submission", async () => {
        const { user } = renderLogin();
        const { useStore } = await import("../store.js");
        const registerSpy = vi
            .spyOn(useStore.getState(), "register")
            .mockResolvedValueOnce(undefined);

        await user.click(screen.getByRole("button", { name: "Register" }));

        const emailInput = screen.getByPlaceholderText("Email");
        const passwordInput = screen.getByPlaceholderText("Password (min 8 characters)");
        const submitButton = screen.getByRole("button", { name: "Create account" });

        await user.type(emailInput, "newuser@test.com");
        await user.type(passwordInput, "password123");
        await user.click(submitButton);

        await waitFor(() => {
            expect(registerSpy).toHaveBeenCalledWith("newuser@test.com", "password123");
        });

        registerSpy.mockRestore();
    });

    it("prevents form submission when email is empty", async () => {
        const { user } = renderLogin();
        const passwordInput = screen.getByPlaceholderText("Password");
        const submitButton = screen.getByRole("button", { name: "Sign in" });

        await user.type(passwordInput, "password");
        await user.click(submitButton);

        const emailInput = screen.getByPlaceholderText("Email");
        expect(emailInput).toBeInvalid();
    });

    it("prevents form submission when password is empty", async () => {
        const { user } = renderLogin();
        const emailInput = screen.getByPlaceholderText("Email");
        const submitButton = screen.getByRole("button", { name: "Sign in" });

        await user.type(emailInput, "user@test.com");
        await user.click(submitButton);

        const passwordInput = screen.getByPlaceholderText("Password");
        expect(passwordInput).toBeInvalid();
    });

    it("asks the browser for an 8-character password when registering only", async () => {
        const { user } = renderLogin();
        expect(screen.getByPlaceholderText("Password")).not.toHaveAttribute("minlength");

        await user.click(screen.getByRole("button", { name: "Register" }));
        expect(screen.getByPlaceholderText("Password (min 8 characters)")).toHaveAttribute(
            "minlength",
            "8",
        );

        await user.click(screen.getByRole("button", { name: "Sign in" }));
        expect(screen.getByPlaceholderText("Password")).not.toHaveAttribute("minlength");
    });

    it("ignores a second submit while the first request is still in flight", async () => {
        const { user } = renderLogin();
        const { useStore } = await import("../store.js");
        let release = () => {};
        const login = vi
            .spyOn(useStore.getState(), "login")
            .mockImplementation(() => new Promise((resolve) => (release = resolve)));

        await user.type(screen.getByPlaceholderText("Email"), "user@test.com");
        await user.type(screen.getByPlaceholderText("Password"), "password");
        const form = document.querySelector<HTMLElement>("form")!;
        fireEvent.submit(form);
        fireEvent.submit(form);

        expect(login).toHaveBeenCalledExactlyOnceWith("user@test.com", "password");
        release();
        await waitFor(() => expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled());
    });

    it("opens docs, demo and GitHub in a new tab", () => {
        renderLogin();
        const links = screen
            .getAllByRole("link")
            .map((a) => [a.textContent, a.getAttribute("href"), a.getAttribute("target")]);
        expect(links).toEqual([
            ["Docs", "/docs", "_blank"],
            ["Demo", "/demo", "_blank"],
            ["GitHub", "https://github.com/alchemmist/monori", "_blank"],
        ]);
    });

    it("returns to the saved internal location and replaces the login history entry", async () => {
        const { useStore } = await import("../store.js");
        vi.spyOn(useStore.getState(), "login").mockResolvedValueOnce(undefined);
        const { user } = renderLogin(
            [
                "/previous",
                {
                    pathname: "/login",
                    state: {
                        from: {
                            pathname: "/transactions",
                            search: "?query=rent",
                            hash: "#recent",
                        },
                    },
                },
            ],
            1,
        );

        await user.type(screen.getByPlaceholderText("Email"), "user@test.com");
        await user.type(screen.getByPlaceholderText("Password"), "password");
        await user.click(screen.getByRole("button", { name: "Sign in" }));

        expect(await screen.findByTestId("current-location")).toHaveTextContent(
            "/transactions?query=rent#recent",
        );
        await user.click(screen.getByRole("button", { name: "Back in test history" }));
        expect(await screen.findByTestId("current-location")).toHaveTextContent("/previous");
    });

    it("returns to Budget when no saved location exists", async () => {
        const { useStore } = await import("../store.js");
        vi.spyOn(useStore.getState(), "login").mockResolvedValueOnce(undefined);
        const { user } = renderLogin();

        await user.type(screen.getByPlaceholderText("Email"), "user@test.com");
        await user.type(screen.getByPlaceholderText("Password"), "password");
        await user.click(screen.getByRole("button", { name: "Sign in" }));

        expect(await screen.findByTestId("current-location")).toHaveTextContent("/budget");
    });

    it.each(["//attacker.example", "https://attacker.example"])(
        "rejects an external saved destination: %s",
        async (pathname) => {
            const { useStore } = await import("../store.js");
            vi.spyOn(useStore.getState(), "login").mockResolvedValueOnce(undefined);
            const { user } = renderLogin([
                {
                    pathname: "/login",
                    state: { from: { pathname, search: "", hash: "" } },
                },
            ]);

            await user.type(screen.getByPlaceholderText("Email"), "user@test.com");
            await user.type(screen.getByPlaceholderText("Password"), "password");
            await user.click(screen.getByRole("button", { name: "Sign in" }));

            expect(await screen.findByTestId("current-location")).toHaveTextContent("/budget");
        },
    );

    it.each([
        ["a primitive router state", "invalid"],
        ["a string destination", { from: "/transactions" }],
        ["a missing pathname", { from: { search: "", hash: "" } }],
        ["a non-string pathname", { from: { pathname: 1, search: "", hash: "" } }],
        ["a non-string search", { from: { pathname: "/budget", search: 1, hash: "" } }],
        ["a non-string hash", { from: { pathname: "/budget", search: "", hash: 1 } }],
    ])("returns to Budget for %s", async (_description, state) => {
        const { useStore } = await import("../store.js");
        vi.spyOn(useStore.getState(), "login").mockResolvedValueOnce(undefined);
        const { user } = renderLogin([{ pathname: "/login", state }]);

        await user.type(screen.getByPlaceholderText("Email"), "user@test.com");
        await user.type(screen.getByPlaceholderText("Password"), "password");
        await user.click(screen.getByRole("button", { name: "Sign in" }));

        expect(await screen.findByTestId("current-location")).toHaveTextContent(/^\/budget$/);
    });
});
