import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import localModelPlugin from './scripts/local-model-plugin.mjs'

export default defineConfig({
  plugins: [react(), localModelPlugin()],
  server: { host: 'localhost', port: 5173, strictPort: true },
  preview: { host: 'localhost', port: 4173, strictPort: true },
})
