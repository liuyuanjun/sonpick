import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const apiPort = process.env.VITE_API_PORT || '8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': `http://127.0.0.1:${apiPort}`,
      '/ws': {
        target: `ws://127.0.0.1:${apiPort}`,
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
