import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./test/setup.js'],
    include: ['**/*.test.js', '**/*.test.jsx'],
    globals: true,
    // Non-watch mode is default when --run passed
  },
});
