import { useEffect, useState } from "react";
import { ThemeProvider } from "@gravity-ui/uikit";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";

export default function Root() {
  const [theme, setTheme] = useState(() => localStorage.getItem("docs_theme") || "light");
  const toggleTheme = () =>
    setTheme((t) => {
      const next = t === "light" ? "dark" : "light";
      localStorage.setItem("docs_theme", next);
      return next;
    });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  return (
    <ThemeProvider theme={theme}>
      <BrowserRouter basename="/docs">
        <App theme={theme} onToggleTheme={toggleTheme} />
      </BrowserRouter>
    </ThemeProvider>
  );
}
