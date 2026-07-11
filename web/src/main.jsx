import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import { ThemeProvider, ToasterProvider, ToasterComponent, Toaster } from "@gravity-ui/uikit";
import "@gravity-ui/uikit/styles/fonts.css";
import "@gravity-ui/uikit/styles/styles.css";
import "./theme.css";
import "./app.css";
import App from "./App.jsx";

const toaster = new Toaster();

function Root() {
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

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
