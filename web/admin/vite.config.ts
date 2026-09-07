import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const certDir = resolve(process.cwd(), "../../.certs");
const keyPath = resolve(certDir, "localhost-key.pem");
const certPath = resolve(certDir, "localhost.pem");
const https =
  existsSync(keyPath) && existsSync(certPath)
    ? { key: readFileSync(keyPath), cert: readFileSync(certPath) }
    : undefined;

export default defineConfig({
  plugins: [react()],
  server: { host: "localhost", port: 5174, strictPort: true, https },
});
