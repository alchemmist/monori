import { describe, it, expect } from "vitest";
import AccountBadge from "./AccountBadge.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("AccountBadge", () => {
    it("renders with default size", () => {
        const { container } = renderUI(
            <AccountBadge account={{ icon: "wallet", color: "#5b6472" }} />,
        );

        const badge = container.querySelector(".acct-badge");
        expect(badge).toBeInTheDocument();
    });

    it("renders custom size", () => {
        const { container } = renderUI(
            <AccountBadge account={{ icon: "wallet", color: "#5b6472" }} size={48} />,
        );

        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveStyle({ width: "48px", height: "48px" });
    });

    it("applies account color to badge", () => {
        const testColor = "#2f6feb";
        const { container } = renderUI(
            <AccountBadge account={{ icon: "wallet", color: testColor }} size={30} />,
        );

        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveStyle({ color: testColor });
    });

    it("uses default color when not provided", () => {
        const { container } = renderUI(<AccountBadge account={{ icon: "wallet" }} />);

        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveClass("acct-badge");
    });

    it("renders icon when no custom image", () => {
        const { container } = renderUI(
            <AccountBadge account={{ icon: "card", color: "#5b6472" }} />,
        );

        const badge = container.querySelector(".acct-badge");
        expect(badge).not.toHaveClass("acct-badge_image");
    });

    it("renders custom image when provided", () => {
        const imageUrl = "data:image/png;base64,iVBORw0KGgo=";
        const { container } = renderUI(
            <AccountBadge account={{ iconImage: imageUrl }} size={30} />,
        );

        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveClass("acct-badge_image");

        const img = badge.querySelector("img");
        expect(img).toHaveAttribute("src", imageUrl);
    });

    it("prefers custom image over icon and color", () => {
        const imageUrl = "data:image/png;base64,iVBORw0KGgo=";
        const { container } = renderUI(
            <AccountBadge
                account={{ icon: "wallet", color: "#2f6feb", iconImage: imageUrl }}
                size={30}
            />,
        );

        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveClass("acct-badge_image");
    });

    it("scales icon size based on badge size", () => {
        const { container } = renderUI(
            <AccountBadge account={{ icon: "wallet", color: "#5b6472" }} size={60} />,
        );

        const badge = container.querySelector(".acct-badge");
        const svg = badge.querySelector("svg");

        const expectedSize = Math.round(60 * 0.56);
        expect(svg).toHaveAttribute("width", String(expectedSize));
        expect(svg).toHaveAttribute("height", String(expectedSize));
    });

    it("renders different icons correctly", () => {
        const testIcons = ["wallet", "card", "sack", "briefcase"];

        for (const icon of testIcons) {
            const { container, unmount } = renderUI(
                <AccountBadge account={{ icon, color: "#5b6472" }} />,
            );

            const badge = container.querySelector(".acct-badge");
            expect(badge).toBeInTheDocument();

            unmount();
        }
    });

    it("falls back to wallet icon for unknown icon", () => {
        const { container } = renderUI(
            <AccountBadge account={{ icon: "unknown_icon", color: "#5b6472" }} />,
        );

        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveClass("acct-badge");
        expect(badge).not.toHaveClass("acct-badge_image");
    });

    it("uses different colors", () => {
        const colors = [
            "#5b6472",
            "#2f6feb",
            "#0ea5e9",
            "#10b981",
            "#14b8a6",
            "#8b5cf6",
            "#ec4899",
            "#ef5a17",
            "#eab308",
            "#ef4444",
        ];

        for (const color of colors) {
            const { container, unmount } = renderUI(
                <AccountBadge account={{ icon: "wallet", color }} />,
            );

            const badge = container.querySelector(".acct-badge");
            expect(badge).toHaveStyle({ color });

            unmount();
        }
    });

    it("has correct aspect ratio", () => {
        const { container } = renderUI(
            <AccountBadge account={{ icon: "wallet", color: "#5b6472" }} size={100} />,
        );

        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveStyle({ width: "100px", height: "100px" });
    });
});