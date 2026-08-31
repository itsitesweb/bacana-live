import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

export default defineConfig(() => {
  return {
	build: {
		chunkSizeWarningLimit: 1600,
	},
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      hmr: process.env.DISABLE_HMR !== 'true',
      watch: {
        ignored: [
          '**/data/**',
          '**/radar/**',
          '**/.browser_data/**',
          '**/logs/**',
          '**/*.pyc',
          '**/__pycache__/**',
          '**/*.log',
          '**/crawler_catalog_cache.json',
          '**/bacanalive_config.json',
          '**/matches.json',
        ],
      },
    },
  };
});
