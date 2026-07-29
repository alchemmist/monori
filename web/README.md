# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.

## Testing

Component tests render one screen in jsdom under vitest (`environment: "jsdom"`), interact like a user, and assert on the DOM. Run them with `npx vitest run` (or `npx vitest run --coverage`); the same runner drives the Stryker mutation gate, so new tests are kept honest.

Use the helpers in `src/test/render.jsx`:

- `renderUI(ui)` wraps the tree in the app's `MantineProvider` (light theme, `env="test"` to drop mount transitions) plus `Notifications`, and returns `{ user, ...result }` where `user` is a `userEvent` session with `delay: null`.
- The zustand store in `src/store.js` is the app's only data source. Fill it two ways:
    - `atDemo()` puts the app on `/demo`, where the store runs entirely off the bundled sample dataset and never touches the network — this is what page tests use, so they exercise the real store code paths.
    - `seed({ ... })` writes a minimal hand-built snapshot straight into the store, for empty states and edge shapes the demo data does not contain.
- Anything that must hit the server is tested by mocking `src/api.js` directly (`vi.spyOn(api, "...")`), not a network layer.
- `resetStore()` between tests, since zustand keeps state on the module, not the React tree.

Tests assert user-visible behavior (roles, text, DOM state), not implementation details. Decorative canvases (`Meadow.jsx`, `GlyphFlower.jsx`) and full-stack journeys owned by the e2e suite are out of scope here.
