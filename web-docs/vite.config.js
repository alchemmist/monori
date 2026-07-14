import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/docs/" : "/",
  plugins: [react()],
  server: {
    port: 5175,
    fs: { allow: [".."] },
  },
}));
