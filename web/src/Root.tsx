import { Suspense, lazy, useEffect, useLayoutEffect, useState } from "react";
import { Loader, MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import App from "./App.jsx";
import Shell from "./components/Shell.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import LogoutPage from "./pages/LogoutPage.jsx";
import NotFound from "./components/NotFound.jsx";
import { useStore } from "./store.js";
import { theme as mantineTheme } from "./ui/theme.js";
import type { ThemeMode } from "./types.js";

// the marketing/docs bundle (react-markdown and friends) is not needed inside
// the app itself, so it loads on demand
const Landing = lazy(() => import("./components/Landing.jsx"));
const MarkdownPage = lazy(() => import("./components/MarkdownPage.jsx"));
const DiagramPage = lazy(() => import("./components/DiagramPage.jsx"));

function LoginRoute() {
    const { user, authChecked, checkAuth } = useStore();

    useEffect(() => {
        if (!authChecked) void checkAuth();
    }, [authChecked, checkAuth]);

    if (!authChecked) {
        return (
            <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
                <Loader size="lg" type="bars" />
            </div>
        );
    }
    if (user) return <Navigate to="/budget" replace />;
    return <LoginPage />;
}

// one theme for the whole site (landing, docs, auth, app), persisted under a
// single localStorage key so it never diverges between routes
function readTheme(): ThemeMode {
    try {
        return localStorage.getItem("theme") === "dark" ? "dark" : "light";
    } catch {
        return "light";
    }
}

function storeTheme(value: ThemeMode) {
    try {
        localStorage.setItem("theme", value);
    } catch {
        /* storage unavailable (private mode, sandboxed) — theme just won't persist */
    }
}

export default function Root() {
    const [theme, setTheme] = useState(readTheme);
    const toggleTheme = () =>
        setTheme((t) => {
            const next = t === "light" ? "dark" : "light";
            storeTheme(next);
            return next;
        });

    // the whole app keys its dark variant off body.theme-dark; keep that class in
    // sync with the theme state (an inline script in index.html sets it pre-paint)
    useLayoutEffect(() => {
        document.body.classList.toggle("theme-dark", theme === "dark");
    }, [theme]);

    // MantineProvider drives its own dark styles via data-mantine-color-scheme
    const app = <App theme={theme} onToggleTheme={toggleTheme} />;

    return (
        <MantineProvider theme={mantineTheme} forceColorScheme={theme}>
            <BrowserRouter>
                <Suspense
                    fallback={
                        <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
                            <Loader size="lg" type="bars" />
                        </div>
                    }
                >
                    <Routes>
                        {/* marketing landing + documentation share the docs Shell */}
                        <Route element={<Shell theme={theme} onToggleTheme={toggleTheme} />}>
                            <Route path="/welcome" element={<Landing />} />
                            <Route
                                path="/docs"
                                element={<Navigate to="/docs/getting-started" replace />}
                            />
                            <Route path="/docs/:slug" element={<MarkdownPage />} />
                        </Route>
                        {/* the diagram viewer owns the whole viewport, so it sits outside the Shell */}
                        <Route path="/docs/:slug/diagram/:index" element={<DiagramPage />} />
                        <Route path="/" element={app} />
                        <Route path="/login" element={<LoginRoute />} />
                        <Route path="/logout" element={<LogoutPage />} />
                        <Route path="/demo" element={app} />
                        <Route path="/demo/:page" element={app} />
                        <Route path="/budget" element={app} />
                        <Route path="/dashboard" element={app} />
                        <Route path="/transactions" element={app} />
                        <Route path="/accounts" element={app} />
                        <Route path="/categories" element={app} />
                        <Route path="/settings" element={app} />
                        <Route path="/admin" element={app} />
                        <Route path="*" element={<NotFound />} />
                    </Routes>
                </Suspense>
            </BrowserRouter>
            <Notifications position="bottom-right" />
        </MantineProvider>
    );
}
