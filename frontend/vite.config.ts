import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      // Same-origin from the browser's point of view — avoids needing CORS
      // on the Phase 1 API. Target is the docker-compose service name so
      // this works from inside the frontend container; see docker-compose.dev.yml.
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://quant-hub-api:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
