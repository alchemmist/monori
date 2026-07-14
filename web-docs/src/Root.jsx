import { useEffect, useState } from "react";
import { ThemeProvider } from "@gravity-ui/uikit";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";

function readTheme() {
  try {
    return localStorage.getItem("docs_theme") || "light";
  } catch {
    return "light";
  }
}

function storeTheme(value) {
  try {
    localStorage.setItem("docs_theme", value);
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
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
        <App theme={theme} onToggleTheme={toggleTheme} />
      </BrowserRouter>
    </ThemeProvider>
  );
}
