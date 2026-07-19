import { Routes, Route, Navigate } from "react-router-dom";
import Shell from "./components/Shell.jsx";
import Landing from "./components/Landing.jsx";
import MarkdownPage from "./components/MarkdownPage.jsx";

export default function App({ theme, onToggleTheme }) {
    return (
        <Routes>
            <Route element={<Shell theme={theme} onToggleTheme={onToggleTheme} />}>
                <Route index element={<Navigate to="/getting-started" replace />} />
                <Route path="welcome" element={<Landing />} />
                <Route path=":slug" element={<MarkdownPage />} />
            </Route>
        </Routes>
    );
}
