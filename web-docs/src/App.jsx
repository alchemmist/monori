import { Routes, Route, Navigate } from "react-router-dom";
import Shell from "./components/Shell.jsx";
import Landing from "./components/Landing.jsx";
import MarkdownPage from "./components/MarkdownPage.jsx";

export default function App({ theme, onToggleTheme }) {
    return (
        <Routes>
            <Route element={<Shell theme={theme} onToggleTheme={onToggleTheme} />}>
                <Route path="/welcome" element={<Landing />} />
                <Route path="/docs" element={<Navigate to="/docs/getting-started" replace />} />
                <Route path="/docs/:slug" element={<MarkdownPage />} />
                <Route path="*" element={<Navigate to="/docs/getting-started" replace />} />
            </Route>
        </Routes>
    );
}
