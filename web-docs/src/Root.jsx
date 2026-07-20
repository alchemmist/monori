import { useEffect, useState } from "react";
import { ThemeProvider } from "@gravity-ui/uikit";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";

// same localStorage key as the web app so the theme carries across the whole
// site (landing/docs and the app share one origin in production): toggling dark
// on /welcome must survive the jump to /login
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

    useEffect(() => {
        document.documentElement.dataset.theme = theme;
    }, [theme]);

    return (
        <ThemeProvider theme={theme}>
            <BrowserRouter>
                <App theme={theme} onToggleTheme={toggleTheme} />
            </BrowserRouter>
        </ThemeProvider>
    );
}
