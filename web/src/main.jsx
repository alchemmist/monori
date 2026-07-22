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

ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
        <Root />
    </React.StrictMode>,
);
