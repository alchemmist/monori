/* Inline text with the app's semantic tones (replaces gravity <Text>). */
export default function Txt({ tone, caption = false, block = false, className = "", ...rest }) {
    const Tag = block ? "div" : "span";
    const classes = [tone ? `t-${tone}` : "", caption ? "t-caption" : "", className]
        .filter(Boolean)
        .join(" ");
    return <Tag className={classes || undefined} {...rest} />;
}
