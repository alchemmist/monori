import { TextInput } from "@mantine/core";
import { TextareaAutosize } from "../../node_modules/@mantine/core/esm/components/Textarea/Autosize.mjs";

import InlineSelect from "./InlineSelect.jsx";
import useAmountField from "./useAmountField.js";

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

/* Money field: same look as FTextInput, but the digits group as they are typed.
 * onChange hands back the text itself — there is no event worth passing on. */
export function FAmountInput({ value, onChange, ...props }) {
    const amount = useAmountField(onChange);
    return <TextInput classNames={cls} value={value} {...amount} {...props} />;
}

export function FTextArea(props) {
    return (
        <div className="mi-input">
            <TextareaAutosize className="mi-input__field" {...props} />
        </div>
    );
}

/* Form-row face of the one shared select: same InlineSelect engine and the
 * same frosted-glass dropdown as everywhere else, styled as a labelled field. */
export function FSelect({ placeholder = "—", ...props }) {
    return <InlineSelect field placeholder={placeholder} {...props} />;
}
