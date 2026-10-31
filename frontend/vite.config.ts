import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * Vite configuration.
 *
 * Dev server proxies /api/* to the FastAPI backend so the frontend can use
 * relative paths (/api/health) in both development and production.
 *
 * VITE_PROXY_TARGET is set to http://backend:8000 inside docker-compose so
 * requests are forwarded to the correct container name.  Locally it falls
 * back to http://localhost:8000.
 */
export default defineConfig({
  plugins: [react()],
  build: {
    // Recharts + React Router push the bundle just over 500 kB; raise the
    // warning threshold so the build output stays clean.
    chunkSizeWarningLimit: 700,
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
