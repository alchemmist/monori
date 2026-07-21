import React from "react";
import ReactDOM from "react-dom/client";
import "@gravity-ui/uikit/styles/fonts.css";
import "@gravity-ui/uikit/styles/styles.css";
import "@mantine/core/styles.css";
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
