import { defineConfig } from 'vite';

// 渲染层只消费 L2 下发的 snapshot/delta/event；开发期把 /ws 与 /sessions 代理到会话层（L2）。
//
// D-9（rev2 / 3A-M3·M4）：
//   - `build.outDir` = `<workspace>/.build/web`（**在 02_source 之外**）⇒ `02_source` 内零 `dist/`；
//   - `build.emptyOutDir: true`：outDir 在项目根之外时 vite **不会**自动清空，
//     会跨构建累积陈旧 bundle（污染浏览器验收证据链）。**必须在第一次 build 之前**就位。
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8787', ws: true },
      '/sessions': { target: 'http://127.0.0.1:8787', changeOrigin: true },
      // M4 / W12：内核只读实时观察通道（`cli live`，默认 8899）。**只读 GET/SSE**。
      '/live': { target: 'http://127.0.0.1:8899', changeOrigin: true, ws: false },
    },
  },
  build: {
    outDir: '../../../.build/web',
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: true,
  },
});
