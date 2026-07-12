import { useState } from "react";
import { ThemeProvider, ToasterProvider, ToasterComponent, Toaster } from "@gravity-ui/uikit";
import App from "./App.jsx";

const toaster = new Toaster();

export default function Root() {
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "light");
  const toggleTheme = () =>
    setTheme((t) => {
      const next = t === "light" ? "dark" : "light";
      localStorage.setItem("theme", next);
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
