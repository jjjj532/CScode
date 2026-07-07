import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxyTarget = `http://localhost:${process.env.CSCORE_SERVER_PORT || '8080'}`

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': proxyTarget,
      '/outputs': proxyTarget,
    },
  },
  build: {
    outDir: 'dist',
  },
})
