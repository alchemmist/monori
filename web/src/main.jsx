import React from "react";
import ReactDOM from "react-dom/client";
import { ThemeProvider, ToasterProvider, ToasterComponent, Toaster } from "@gravity-ui/uikit";
import "@gravity-ui/uikit/styles/fonts.css";
import "@gravity-ui/uikit/styles/styles.css";
import "./theme.css";
import "./app.css";
import App from "./App.jsx";

const toaster = new Toaster();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider theme="light">
      <ToasterProvider toaster={toaster}>
        <App />
        <ToasterComponent />
      </ToasterProvider>
    </ThemeProvider>
  </React.StrictMode>
);
