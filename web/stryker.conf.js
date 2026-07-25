const threshold = Number(process.env.MUTATION_THRESHOLD ?? 85);

export default {
    $schema: "./node_modules/@stryker-mutator/core/schema/stryker-schema.json",
    testRunner: "vitest",
    coverageAnalysis: "perTest",
    // the whole app, not just the engine: coverage says a line ran, mutation
    // says an assertion would have noticed it change, and the components are
    // where that distinction has actually cost us
    mutate: [
        "src/**/*.{js,jsx}",
        "!src/**/*.test.{js,jsx}",
        "!src/main.jsx",
        "!src/test/**",
        // generative canvas art: every mutant lands on a 2d context jsdom does
        // not implement, so they all survive for a reason no test can fix
        "!src/components/Meadow.jsx",
        "!src/components/GlyphFlower.jsx",
        // bundled sample data, not logic
        "!src/demo/**",
    ],
    reporters: ["clear-text", "progress"],
    concurrency: 4,
    // the docs pages glob ../../docs/*.md, which a sandbox copy of web/ alone
    // cannot resolve; mutating in place keeps that path real (stryker restores
    // the originals when the run ends)
    inPlace: true,
    // jsdom mounts are slower than the engine's pure functions, and a mutant
    // that puts a component into an infinite render loop must time out rather
    // than hang the run
    timeoutMS: 30000,
    timeoutFactor: 3,
    // the dry run mounts every component test once under instrumentation; the
    // 5-minute default is an engine-sized budget, not an app-sized one
    dryRunTimeoutMinutes: 30,
    thresholds: { high: Math.min(100, threshold + 5), low: threshold, break: threshold },
};
