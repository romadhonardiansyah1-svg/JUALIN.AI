import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('.', import.meta.url)),
    },
  },
  esbuild: {
    jsx: 'automatic',
    loader: 'jsx',
    include: /\/(app|components)\/.*\.jsx?$/,
    exclude: [],
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./test/setup.js'],
    include: ['**/*.test.js', '**/*.test.jsx'],
    globals: true,
    // Non-watch mode is default when --run passed
  },
});
