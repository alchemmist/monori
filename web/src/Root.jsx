import { Suspense, lazy, useLayoutEffect, useState } from "react";
import { Loader, MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import App from "./App.jsx";
import Shell from "./components/Shell.jsx";
import { theme as mantineTheme } from "./ui/theme.js";

// the marketing/docs bundle (react-markdown and friends) is not needed inside
// the app itself, so it loads on demand
const Landing = lazy(() => import("./components/Landing.jsx"));
const MarkdownPage = lazy(() => import("./components/MarkdownPage.jsx"));

// one theme for the whole site (landing, docs, auth, app), persisted under a
// single localStorage key so it never diverges between routes
function readTheme() {
    try {
        return localStorage.getItem("theme") || "light";
    } catch {
        return "light";
    }
}

function storeTheme(value) {
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
                        {/* everything else is the app itself (auth, demo, panel) */}
                        <Route
                            path="*"
                            element={<App theme={theme} onToggleTheme={toggleTheme} />}
                        />
                    </Routes>
                </Suspense>
            </BrowserRouter>
            <Notifications position="bottom-right" />
        </MantineProvider>
    );
}
