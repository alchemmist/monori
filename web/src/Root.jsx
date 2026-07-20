import { useState } from "react";
import { ThemeProvider, ToasterProvider, ToasterComponent, Toaster } from "@gravity-ui/uikit";
import App from "./App.jsx";

const toaster = new Toaster();

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

    return (
        <ThemeProvider theme={theme}>
            <ToasterProvider toaster={toaster}>
                <App theme={theme} onToggleTheme={toggleTheme} />
                <ToasterComponent />
            </ToasterProvider>
        </ThemeProvider>
    );
}
