import type { HTMLAttributes } from "react";

interface TagProps extends HTMLAttributes<HTMLSpanElement> {
    theme?: string;
}

/* Small themed chip (the gravity Label look): soft background, 20px tall. */
export default function Tag({ theme = "unknown", className = "", children, ...rest }: TagProps) {
    return (
        <span className={`tag tag_${theme} ${className}`.trim()} {...rest}>
            {children}
        </span>
    );
}
