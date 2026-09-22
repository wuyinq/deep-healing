import { defineConfig } from 'vite';

// 渲染层只消费 L2 下发的 snapshot/delta/event；开发期把 /ws 代理到会话层（L2）。
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8787', ws: true },
      '/sessions': { target: 'http://127.0.0.1:8787', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    target: 'es2022',
    sourcemap: true,
  },
});
