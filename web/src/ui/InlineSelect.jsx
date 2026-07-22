import { useState } from "react";
import { Combobox, useCombobox } from "@mantine/core";
import { ChevronDown } from "@gravity-ui/icons";

/* Auto-width select rendered as a button (value + chevron hugging), the way
 * the gravity Select control looked. `borderless` drops the border for table
 * rows, `small` is the compact 24px size, `searchable` adds a search box on
 * top of the dropdown. */
export default function InlineSelect({
    value,
    onChange,
    data,
    searchable = false,
    placeholder = "—",
    small = false,
    borderless = false,
    className = "",
}) {
    const [search, setSearch] = useState("");
    const combobox = useCombobox({
        onDropdownClose: () => {
            combobox.resetSelectedOption();
            setSearch("");
        },
    });
    const opts = data.map((o) => (typeof o === "string" ? { value: o, label: o } : o));
    const current = opts.find((o) => o.value === value);
    const q = search.trim().toLowerCase();
    const shown = q ? opts.filter((o) => o.label.toLowerCase().includes(q)) : opts;

    return (
        <Combobox
            store={combobox}
            position="bottom-start"
            shadow="md"
            offset={4}
            width={220}
            onOptionSubmit={(v) => {
                onChange(v);
                combobox.closeDropdown();
            }}
        >
            <Combobox.Target>
                <button
                    type="button"
                    className={[
                        "gsel",
                        small && "gsel_s",
                        borderless && "gsel_borderless",
                        className,
                    ]
                        .filter(Boolean)
                        .join(" ")}
                    onClick={() => combobox.toggleDropdown()}
                >
                    <span className={`gsel__text${current ? "" : " gsel__text_empty"}`}>
                        {current?.label ?? placeholder}
                    </span>
                    <ChevronDown width={14} height={14} className="gsel__chev" />
                </button>
            </Combobox.Target>
            <Combobox.Dropdown className="gsel__drop">
                {/* the dropdown node stays mounted (hidden) for every instance, so
                    with dozens of row selects the options only render while open */}
                {combobox.dropdownOpened && (
                    <>
                        {searchable && (
                            <Combobox.Search
                                value={search}
                                onChange={(e) => setSearch(e.currentTarget.value)}
                                placeholder="Search"
                            />
                        )}
                        <Combobox.Options style={{ maxHeight: 264, overflowY: "auto" }}>
                            {shown.length === 0 && <Combobox.Empty>Nothing found</Combobox.Empty>}
                            {shown.map((o) => (
                                <Combobox.Option
                                    key={o.value}
                                    value={o.value}
                                    data-selected={o.value === value || undefined}
                                >
                                    {o.label}
                                </Combobox.Option>
                            ))}
                        </Combobox.Options>
                    </>
                )}
            </Combobox.Dropdown>
        </Combobox>
    );
}
