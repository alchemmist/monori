import { Textarea, TextInput } from "@mantine/core";

import InlineSelect from "./InlineSelect.jsx";

/* Gravity-style form fields: the label sits INSIDE the bordered box, inline
 * with the value (see ui/mantine.css .mi-input). */
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

/* Form-row face of the one shared select: same InlineSelect engine and the
 * same frosted-glass dropdown as everywhere else, styled as a labelled field. */
export function FSelect({ placeholder = "—", ...props }) {
    return <InlineSelect field placeholder={placeholder} {...props} />;
}
