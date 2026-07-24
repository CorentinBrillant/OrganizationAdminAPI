import { defineConfig } from 'vitest/config'

export default defineConfig({
  cacheDir: '/tmp/frontend-vite-cache',
  esbuild: {
    jsx: 'automatic',
    jsxImportSource: 'react',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/tests/setup.js',
    clearMocks: true,
  },
  cache: {
    dir: '/tmp/vitest-frontend-cache',
  },
})
