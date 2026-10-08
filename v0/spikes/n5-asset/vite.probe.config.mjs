/**
 * 取证专用 vite 配置（N5 / **非交付面**）：**不改交付树里的 `web/vite.config.ts`**。
 *
 * 与交付配置的差别：只多一条 `/packs` 代理（指向 `serve_packs.py`），使真浏览器能取到
 * 内容包（`worldview.json` / `npcs/*.json` / `assets/**`）。其余（port / build.outDir）不动。
 *
 * 运行：`node <ws>/node_modules/vite/bin/vite.js --config <ws>/v0/spikes/n5-asset/vite.probe.config.mjs`
 */
import { defineConfig } from 'vite';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(HERE, '../../02_source/v0_skeleton/web');

export default defineConfig({
  root: WEB,
  /**
   * N5-r3：vite 的依赖预打包缓存默认落在 `<root>/node_modules/.vite` ⇒ 会在**交付面**
   * （`v0/02_source/v0_skeleton/web/node_modules`）留残渣，打红 §7e「构建/依赖产物零残渣」。
   * 显式把 `cacheDir` 挪到系统临时目录（取证配置，不改交付树 `web/vite.config.ts`）。
   */
  cacheDir: resolve(process.env.TMPDIR || '/tmp', 'n5-vite-cache'),
  server: {
    port: 5199,
    strictPort: true,
    proxy: {
      '/packs': { target: 'http://127.0.0.1:8791', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8787', ws: true },
      '/sessions': { target: 'http://127.0.0.1:8787', changeOrigin: true },
      '/live': { target: 'http://127.0.0.1:8899', changeOrigin: true, ws: false },
    },
  },
  build: {
    outDir: resolve(WEB, '../../../.build/web'),
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: true,
  },
});
