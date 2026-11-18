import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
    {
        ignores: ["dist/**", "coverage/**", "node_modules/**", "prototypes/**", "reports/**"],
    },
    {
        files: ["src/**/*.{ts,tsx}", "e2e/**/*.ts", "*.config.ts", "stryker.conf.ts"],
        extends: [tseslint.configs.strictTypeChecked, tseslint.configs.stylisticTypeChecked],
        languageOptions: {
            parserOptions: {
                projectService: true,
                tsconfigRootDir: import.meta.dirname,
            },
        },
        plugins: { "react-hooks": reactHooks },
        rules: {
            "@typescript-eslint/array-type": "off",
            "@typescript-eslint/consistent-generic-constructors": "off",
            "@typescript-eslint/consistent-type-definitions": "off",
            "@typescript-eslint/no-confusing-void-expression": "off",
            "@typescript-eslint/no-empty-function": "off",
            "@typescript-eslint/no-non-null-assertion": "off",
            "@typescript-eslint/no-unnecessary-type-assertion": "off",
            "@typescript-eslint/no-unnecessary-type-conversion": "off",
            "@typescript-eslint/prefer-nullish-coalescing": "off",
            "@typescript-eslint/prefer-optional-chain": "off",
            "@typescript-eslint/prefer-regexp-exec": "off",
            "@typescript-eslint/require-await": "off",
            "@typescript-eslint/use-unknown-in-catch-callback-variable": "off",
            "@typescript-eslint/no-floating-promises": "error",
            "@typescript-eslint/no-misused-promises": "error",
            "@typescript-eslint/no-unsafe-argument": "error",
            "@typescript-eslint/no-unsafe-assignment": "error",
            "@typescript-eslint/no-unsafe-call": "error",
            "@typescript-eslint/no-unsafe-declaration-merging": "error",
            "@typescript-eslint/no-unsafe-enum-comparison": "error",
            "@typescript-eslint/no-unsafe-function-type": "error",
            "@typescript-eslint/no-unsafe-member-access": "error",
            "@typescript-eslint/no-unsafe-return": "error",
            "@typescript-eslint/no-unsafe-type-assertion": "error",
            "@typescript-eslint/no-unsafe-unary-minus": "error",
            "@typescript-eslint/strict-boolean-expressions": "error",
            "@typescript-eslint/switch-exhaustiveness-check": "error",
            "@typescript-eslint/no-unnecessary-condition": "error",
            "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
            "react-hooks/exhaustive-deps": "error",
        },
    },
    {
        files: ["src/**/*.test.{ts,tsx}", "e2e/**/*.ts"],
        rules: {
            "@typescript-eslint/no-empty-function": "off",
            "@typescript-eslint/no-non-null-assertion": "off",
            "@typescript-eslint/no-unsafe-type-assertion": "off",
            "@typescript-eslint/require-await": "off",
        },
    },
);
