import { Textarea, TextInput } from "@mantine/core";
import type { ComponentProps } from "react";

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

export function FTextInput(props: ComponentProps<typeof TextInput>) {
    return <TextInput classNames={cls} {...props} />;
}

/* Money field: same look as FTextInput, but the digits group as they are typed.
 * onChange hands back the text itself — there is no event worth passing on. */
interface AmountInputProps extends Omit<ComponentProps<typeof TextInput>, "onChange"> {
    onChange: (value: string) => void;
}

export function FAmountInput({ value, onChange, ...props }: AmountInputProps) {
    const amount = useAmountField(onChange);
    return <TextInput classNames={cls} value={value} {...amount} {...props} />;
}

export function FTextArea(props: ComponentProps<typeof Textarea>) {
    return (
        <div className="mi-input">
            <Textarea autosize className="mi-input__field" {...props} />
        </div>
    );
}

/* Form-row face of the one shared select: same InlineSelect engine and the
 * same frosted-glass dropdown as everywhere else, styled as a labelled field. */
export function FSelect({ placeholder = "—", ...props }: ComponentProps<typeof InlineSelect>) {
    return <InlineSelect field placeholder={placeholder} {...props} />;
}
