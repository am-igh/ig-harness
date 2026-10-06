import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://api:8000" },
    allowedHosts: [".ts.net"],     // her own Tailscale names (iPad access); the port itself stays bound to 127.0.0.1 on the Mac
  },
});
