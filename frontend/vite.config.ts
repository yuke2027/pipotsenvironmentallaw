import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // node_modules/node_modules contains a second install on this workspace;
  // dedupe keeps a single React/antd copy for the prototype pages.
  resolve: { dedupe: ['react', 'react-dom', 'antd', 'echarts', 'react-router-dom', 'dayjs', '@ant-design/icons'] },
  server: { port: 5173, proxy: { '/api': 'http://localhost:58000' },
    allowedHosts: process.env.VITE_ALLOW_DOCKER_HOST === '1' ? ['host.docker.internal'] : [] },
  build: { rollupOptions: { output: { manualChunks: { charts: ['echarts'], ui: ['antd', '@ant-design/icons'], react: ['react', 'react-dom', 'react-router-dom'] } } } },
});
