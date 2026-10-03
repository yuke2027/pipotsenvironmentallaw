import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:58000' } },
  build: { rollupOptions: { output: { manualChunks: { charts: ['echarts'], ui: ['antd', '@ant-design/icons'], react: ['react', 'react-dom', 'react-router-dom'] } } } },
});
