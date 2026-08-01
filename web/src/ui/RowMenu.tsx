import { Fragment, type ReactNode } from "react";
import { ActionIcon, Menu } from "@mantine/core";
import { Ellipsis } from "@gravity-ui/icons";

/* gravity icon-button sizes in px — Mantine only knows xs..xl aliases */
const SIZES = { xs: 20, s: 24, m: 28 };
type MenuSize = keyof typeof SIZES;

export interface RowMenuItem {
    text: string;
    action: () => void;
    theme?: string;
}

const isGrouped = (items: RowMenuItem[] | RowMenuItem[][]): items is RowMenuItem[][] =>
    items.every(Array.isArray);

const isMenuSize = (size: string): size is MenuSize => Object.hasOwn(SIZES, size);

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
    const groups = isGrouped(items) ? items : [items];
    return (
        <Menu>
            <Menu.Target>
                <ActionIcon
                    size={typeof size === "string" && isMenuSize(size) ? SIZES[size] : Number(size)}
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
