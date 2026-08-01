import { Fragment, type ReactNode } from "react";
import { ActionIcon, Menu } from "@mantine/core";
import { Ellipsis } from "@gravity-ui/icons";

/* gravity icon-button sizes in px — Mantine only knows xs..xl aliases */
const SIZES = { xs: 20, s: 24, m: 28 };

export interface RowMenuItem {
    text: string;
    action: () => void;
    theme?: string;
}

interface RowMenuProps {
    items: RowMenuItem[] | RowMenuItem[][];
    size?: keyof typeof SIZES | number | `${number}`;
    className?: string;
    label?: string;
    icon?: ReactNode;
}

/* Row-level "…" menu. `items` is a flat list or a list of groups (rendered
 * with dividers), each item { text, action, theme } like the gravity
 * DropdownMenu it replaced. */
export default function RowMenu({
    items,
    size = "s",
    className,
    label = "Actions",
    icon,
}: RowMenuProps) {
    const groups: RowMenuItem[][] = Array.isArray(items[0])
        ? (items as RowMenuItem[][])
        : [items as RowMenuItem[]];
    return (
        <Menu>
            <Menu.Target>
                <ActionIcon
                    size={
                        typeof size === "string" && size in SIZES
                            ? SIZES[size as keyof typeof SIZES]
                            : Number(size)
                    }
                    variant="subtle"
                    className={className}
                    aria-label={label}
                >
                    {icon ?? <Ellipsis width={16} height={16} />}
                </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
                {groups.map((group, gi) => (
                    <Fragment key={gi}>
                        {gi > 0 && <Menu.Divider />}
                        {group.map((item) => (
                            <Menu.Item key={item.text} data-tone={item.theme} onClick={item.action}>
                                {item.text}
                            </Menu.Item>
                        ))}
                    </Fragment>
                ))}
            </Menu.Dropdown>
        </Menu>
    );
}
