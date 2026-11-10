import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, Vite serves the React app on :5173 and forwards /api/* to FastAPI (:8010 by
// default). The browser only ever talks to one origin, so no CORS setup is needed.
const api = process.env.PREPRADAR_API ?? "http://localhost:8010";
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": api } },
});
