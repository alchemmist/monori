import React from "react";
import ReactDOM from "react-dom/client";
import "@mantine/core/styles.css";
import "@mantine/charts/styles.css";
import "@mantine/notifications/styles.css";
import "./ui/mantine.css";
import "./theme.css";
import "./app.css";
import "./docs.css";
import Root from "./Root.jsx";

const root = document.getElementById("root");
if (!root) throw new Error("root element is missing");

ReactDOM.createRoot(root).render(
    <React.StrictMode>
        <Root />
    </React.StrictMode>,
);
