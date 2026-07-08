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
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom'],
          'vendor-lucide': ['lucide-react'],
          'vendor-xterm': ['@xterm/xterm', '@xterm/addon-fit', '@xterm/addon-web-links'],
          'vendor-markdown': ['react-markdown', 'remark-gfm', 'rehype-highlight'],
          'vendor-highlight': ['highlight.js'],
          'vendor-state': ['zustand'],
          'vendor-tauri': ['@tauri-apps/api', '@tauri-apps/plugin-dialog', '@tauri-apps/plugin-fs'],
        },
      },
    },
    chunkSizeWarningLimit: 1000,
  },
})
