import { useEffect, useRef, useState } from "react";
import { Combobox, useCombobox } from "@mantine/core";
import { ChevronDown } from "@gravity-ui/icons";

const norm = (o) => (typeof o === "string" ? { value: o, label: o } : o);

// grouped data is `[{ group, kind, options: [...] }]`; flat data is a plain
// array of options. Detect the shape so a single component serves both the flat
// account/year filters and the sectioned category picker.
const isGrouped = (data) => data.length > 0 && data[0] && Array.isArray(data[0].options);

/* Auto-width select rendered as a button (value + chevron hugging), the way
 * the gravity Select control looked. `borderless` drops the border for table
 * rows, `small` is the compact 24px size, `searchable` adds a search box on
 * top of the dropdown. Pass grouped data to render labelled sections (used by
 * the transaction category picker); `dropdownClassName` styles the dropdown
 * surface (e.g. frosted glass). */
export default function InlineSelect({
    value,
    onChange,
    data,
    searchable = false,
    placeholder = "—",
    small = false,
    borderless = false,
    className = "",
    dropdownClassName = "",
}) {
    const [search, setSearch] = useState("");
    const optionsRef = useRef(null);
    const combobox = useCombobox({
        onDropdownClose: () => {
            combobox.resetSelectedOption();
            setSearch("");
        },
    });

    const grouped = isGrouped(data);
    const q = search.trim().toLowerCase();
    const match = (o) => o.label.toLowerCase().includes(q);

    // every option flattened, for the button label lookup regardless of shape
    const allOpts = grouped ? data.flatMap((s) => s.options.map(norm)) : data.map(norm);
    const current = allOpts.find((o) => o.value === value);

    // while searching keep a section whose group name matches (show all its
    // options), otherwise filter its options; drop sections left empty
    const sections = grouped
        ? data
              .map((s) => {
                  const groupHit = q && s.group && s.group.toLowerCase().includes(q);
                  const options = (groupHit ? s.options : s.options.filter(match)).map(norm);
                  return { ...s, options };
              })
              .filter((s) => s.options.length > 0)
        : null;
    const flat = grouped ? null : q ? allOpts.filter(match) : allOpts;
    const nothing = grouped ? sections.length === 0 : flat.length === 0;

    // bring the current selection into view when the dropdown opens
    useEffect(() => {
        if (!combobox.dropdownOpened) return;
        optionsRef.current?.querySelector("[data-selected]")?.scrollIntoView({ block: "nearest" });
    }, [combobox.dropdownOpened]);

    const renderOption = (o) => (
        <Combobox.Option key={o.value} value={o.value} data-selected={o.value === value || undefined}>
            {o.label}
        </Combobox.Option>
    );

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
            <Combobox.Dropdown className={`gsel__drop ${dropdownClassName}`.trim()}>
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
                        <Combobox.Options
                            ref={optionsRef}
                            style={{ maxHeight: 264, overflowY: "auto" }}
                        >
                            {nothing && <Combobox.Empty>Nothing found</Combobox.Empty>}
                            {grouped
                                ? sections.map((s) => (
                                      <Combobox.Group
                                          key={s.group}
                                          label={
                                              <span
                                                  className={`gsel__grp gsel__grp_${s.kind ?? "neutral"}`}
                                              >
                                                  {s.group}
                                              </span>
                                          }
                                      >
                                          {s.options.map(renderOption)}
                                      </Combobox.Group>
                                  ))
                                : flat.map(renderOption)}
                        </Combobox.Options>
                    </>
                )}
            </Combobox.Dropdown>
        </Combobox>
    );
}
