import type { HTMLAttributes } from "react";

interface TxtProps extends HTMLAttributes<HTMLElement> {
    tone?: string;
    caption?: boolean;
    block?: boolean;
}

/* Inline text with the app's semantic tones (replaces gravity <Text>). */
export default function Txt({
    tone,
    caption = false,
    block = false,
    className = "",
    ...rest
}: TxtProps) {
    const Tag = block ? "div" : "span";
    const classes = [
        tone == null || tone === "" ? "" : `t-${tone}`,
        caption ? "t-caption" : "",
        className,
    ]
        .filter((classToken) => classToken !== "")
        .join(" ");
    return <Tag className={classes === "" ? undefined : classes} {...rest} />;
}
