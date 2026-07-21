import { Select, Textarea, TextInput } from "@mantine/core";
import { ChevronDown } from "@gravity-ui/icons";

/* Gravity-style form fields: the label sits INSIDE the bordered box, inline
 * with the value (see ui/mantine.css .mi-input). Plain unlabeled selects use
 * ui/InlineSelect.jsx instead. */
const cls = {
    root: "mi-input",
    label: "mi-input__label",
    wrapper: "mi-input__wrap",
    input: "mi-input__field",
    section: "mi-input__section",
};

export function FTextInput(props) {
    return <TextInput classNames={cls} {...props} />;
}

export function FTextArea(props) {
    return <Textarea classNames={cls} {...props} />;
}

export function FSelect(props) {
    return (
        <Select
            classNames={cls}
            rightSection={<ChevronDown width={14} height={14} />}
            rightSectionPointerEvents="none"
            {...props}
        />
    );
}
