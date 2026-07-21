import { Suspense, lazy, useState } from "react";
import { ThemeProvider } from "@gravity-ui/uikit";
import { MantineProvider } from "@mantine/core";
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

    // the gravity ThemeProvider stays for @gravity-ui/charts: its tooltips need
    // the uikit theme context, and it keeps .g-root_theme_* on <body> — the
    // classes every stylesheet keys its dark variant off (goes away with charts)
    return (
        <ThemeProvider theme={theme}>
            <MantineProvider theme={mantineTheme} forceColorScheme={theme}>
                <BrowserRouter>
                    <Suspense fallback={null}>
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
        </ThemeProvider>
    );
}
