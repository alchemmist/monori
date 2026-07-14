import { Routes, Route } from "react-router-dom";
import Shell from "./components/Shell.jsx";
import LandingV1 from "./components/LandingV1.jsx";
import LandingV2 from "./components/LandingV2.jsx";
import LandingV3 from "./components/LandingV3.jsx";
import MarkdownPage from "./components/MarkdownPage.jsx";

export default function App({ theme, onToggleTheme }) {
  return (
    <Routes>
      <Route element={<Shell theme={theme} onToggleTheme={onToggleTheme} />}>
        <Route index element={<LandingV1 />} />
        <Route path="v1" element={<LandingV1 />} />
        <Route path="v2" element={<LandingV2 />} />
        <Route path="v3" element={<LandingV3 />} />
        <Route path=":slug" element={<MarkdownPage />} />
      </Route>
    </Routes>
  );
}
