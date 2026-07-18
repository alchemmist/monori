import {
    Wallet,
    CreditCard,
    CircleRuble,
    CircleDollar,
    Sack,
    Briefcase,
    House,
    ChartLine,
    Percent,
    Gift,
    Star,
    Heart,
} from "@gravity-ui/icons";

/** Curated glyphs an account can wear. The `name` is what's stored in the DB;
 * unknown/legacy names fall back to the wallet. */
export const ACCOUNT_ICONS = [
    { name: "wallet", Icon: Wallet },
    { name: "card", Icon: CreditCard },
    { name: "ruble", Icon: CircleRuble },
    { name: "dollar", Icon: CircleDollar },
    { name: "sack", Icon: Sack },
    { name: "briefcase", Icon: Briefcase },
    { name: "house", Icon: House },
    { name: "chart", Icon: ChartLine },
    { name: "percent", Icon: Percent },
    { name: "gift", Icon: Gift },
    { name: "star", Icon: Star },
    { name: "heart", Icon: Heart },
];

const BY_NAME = new Map(ACCOUNT_ICONS.map((i) => [i.name, i.Icon]));

export function accountIcon(name) {
    return BY_NAME.get(name) ?? Wallet;
}

/** Preset account colors — the glyph and its tile border take the solid color,
 * the tile fill is a translucent tint of it (see AccountBadge). */
export const ACCOUNT_COLORS = [
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

export const DEFAULT_ACCOUNT_COLOR = ACCOUNT_COLORS[0];
