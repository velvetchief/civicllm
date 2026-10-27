import { defineConfig } from "vitest/config";

export default defineConfig({
  // Next uses `jsx: "preserve"`; vitest's esbuild must compile JSX itself.
  esbuild: { jsx: "automatic" },
  test: {
    include: ["lib/**/*.test.ts", "lib/**/*.test.tsx"],
    environment: "node", // pure-logic tests only; no DOM needed
  },
});
