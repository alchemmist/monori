const threshold = Number(process.env.MUTATION_THRESHOLD ?? 85);

export default {
  $schema: "./node_modules/@stryker-mutator/core/schema/stryker-schema.json",
  testRunner: "vitest",
  coverageAnalysis: "perTest",
  mutate: ["src/engine/**/*.js", "!src/engine/**/*.test.js"],
  reporters: ["clear-text", "progress"],
  concurrency: 4,
  thresholds: { high: Math.min(100, threshold + 5), low: threshold, break: threshold },
};
