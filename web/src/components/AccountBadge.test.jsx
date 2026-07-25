import { describe, it, expect } from "vitest";
import { CreditCard, Wallet } from "@gravity-ui/icons";
import AccountBadge from "./AccountBadge.jsx";
import { renderUI } from "../test/render.jsx";

/** The glyph the badge actually painted, as markup, so two icons can be compared. */
function glyphOf(account, props) {
    const { container, unmount } = renderUI(<AccountBadge account={account} {...props} />);
    const svg = container.querySelector(".acct-badge svg").innerHTML;
    unmount();
    return svg;
}

function renderIcon(Icon) {
    const { container, unmount } = renderUI(<Icon width={16} height={16} />);
    const svg = container.querySelector("svg").innerHTML;
    unmount();
    return svg;
}

describe("AccountBadge", () => {
    it("picks the glyph named by account.icon, not by any other field", () => {
        expect(glyphOf({ icon: "card", color: "#2f6feb" })).toBe(renderIcon(CreditCard));
        expect(glyphOf({ icon: "wallet", color: "#2f6feb" })).toBe(renderIcon(Wallet));
        expect(glyphOf({ icon: "card", color: "#2f6feb" })).not.toBe(
            glyphOf({ icon: "wallet", color: "#2f6feb" }),
        );
    });

    it("falls back to the wallet glyph for an unknown icon name", () => {
        expect(glyphOf({ icon: "unknown_icon", color: "#5b6472" })).toBe(renderIcon(Wallet));
    });

    it("is 30px square by default and scales the glyph to 56% of the tile", () => {
        const { container } = renderUI(<AccountBadge account={{ icon: "wallet" }} />);
        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveStyle({ width: "30px", height: "30px" });
        const svg = badge.querySelector("svg");
        expect(svg).toHaveAttribute("width", "17");
        expect(svg).toHaveAttribute("height", "17");
    });

    it("honours an explicit size for both the tile and the glyph", () => {
        const { container } = renderUI(<AccountBadge account={{ icon: "wallet" }} size={60} />);
        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveStyle({ width: "60px", height: "60px" });
        const svg = badge.querySelector("svg");
        expect(svg).toHaveAttribute("width", "34");
        expect(svg).toHaveAttribute("height", "34");
    });

    it("tints the glyph with the account color and its tile with a mix of it", () => {
        const { container } = renderUI(
            <AccountBadge account={{ icon: "wallet", color: "#2f6feb" }} />,
        );
        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveStyle({ color: "#2f6feb" });
        // jsdom normalises the hex inside the color-mix() to rgb()
        expect(badge.style.background).toBe(
            "color-mix(in srgb, rgb(47, 111, 235) 14%, transparent)",
        );
        expect(badge.style.borderColor).toBe(
            "color-mix(in srgb, rgb(47, 111, 235) 42%, transparent)",
        );
    });

    it("uses the default color when the account has none", () => {
        const { container } = renderUI(<AccountBadge account={{ icon: "wallet" }} />);
        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveStyle({ color: "#5b6472" });
        expect(badge.style.background).toBe(
            "color-mix(in srgb, rgb(91, 100, 114) 14%, transparent)",
        );
    });

    it("shows an uploaded image instead of any glyph or tint", () => {
        const imageUrl = "data:image/png;base64,iVBORw0KGgo=";
        const { container } = renderUI(
            <AccountBadge
                account={{ icon: "wallet", color: "#2f6feb", iconImage: imageUrl }}
                size={40}
            />,
        );
        const badge = container.querySelector(".acct-badge");
        expect(badge).toHaveClass("acct-badge_image");
        expect(badge).toHaveStyle({ width: "40px", height: "40px" });
        expect(badge.querySelector("img")).toHaveAttribute("src", imageUrl);
        expect(badge.querySelector("svg")).toBeNull();
        expect(badge.style.background).toBe("");
    });
});
