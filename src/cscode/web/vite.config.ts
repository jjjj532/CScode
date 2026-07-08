import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { DEFAULT_SERVER_PORT } from './src/config'

const proxyTarget = `http://localhost:${process.env.CSCORE_SERVER_PORT || DEFAULT_SERVER_PORT}`

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
