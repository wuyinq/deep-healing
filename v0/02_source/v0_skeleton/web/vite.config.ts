import { defineConfig, type Plugin } from 'vite';
import { copyFileSync, mkdirSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// 渲染层只消费 L2 下发的 snapshot/delta/event；开发期把 /ws 与 /sessions 代理到会话层（L2）。
//
// D-9（rev2 / 3A-M3·M4）：
//   - `build.outDir` = `<workspace>/.build/web`（**在 02_source 之外**）⇒ `02_source` 内零 `dist/`；
//   - `build.emptyOutDir: true`：outDir 在项目根之外时 vite **不会**自动清空，
//     会跨构建累积陈旧 bundle（污染浏览器验收证据链）。**必须在第一次 build 之前**就位。
//
// FU-20260924-007（M1）· **交付构建丢人物资产**：
//   - 缺陷：`web/assets/**` 里的运行时资产不在 vite 的模块图里（`asset_binding.ts` 的 `glb_url`
//     是**纯字符串 URL**，打包器看不见）⇒ `vite build` 不把它们 emit 进产物 ⇒ 真浏览器
//     `404 GET /assets/character/xuqin-body.glb` ⇒ 角色回落盒体。
//   - 机制：内联插件 `fu007-emit-runtime-assets`（`apply: 'build'`）把 `web/assets/**` **全量递归**
//     复制到 `<outDir>/assets/**`，**运行时 URL 契约逐字节不变**（仍为 `assets/character/xuqin-body.glb`）。
//   - `build.assetsDir` 迁到 `'assets/_bundle'`：打包 JS/CSS 与运行时资产分属**不相交子树**，
//     不依赖「文件名恰好不同」这种脆弱前提（`_bundle` 与 `web/assets/**` 的 14 个一级项均不重名）。
//   - 该插件只在 `vite build` 生效 ⇒ **不影响 `vite dev` 的既有行为**。
const WEB_ROOT = dirname(fileURLToPath(import.meta.url));
const RUNTIME_ASSETS_ROOT = join(WEB_ROOT, 'assets');

/** 递归复制目录树（保留子目录结构；覆盖写 ⇒ 幂等；**不**删除目标侧既有内容）。 */
function copyTree(srcDir: string, destDir: string, skipped: string[]): void {
  mkdirSync(destDir, { recursive: true });
  for (const entry of readdirSync(srcDir, { withFileTypes: true })) {
    const src = join(srcDir, entry.name);
    const dest = join(destDir, entry.name);
    if (entry.isDirectory()) {
      copyTree(src, dest, skipped);
    } else if (entry.isFile()) {
      copyFileSync(src, dest);
    } else {
      // 符号链接等非常规条目**不跟随**：复制面严格限定在 `web/assets` 之内，
      // 避免把 workspace 之外的内容带进分发面（Raven R-5）。
      skipped.push(src);
    }
  }
}

function emitRuntimeAssets(): Plugin {
  let outDir = '';
  return {
    name: 'fu007-emit-runtime-assets',
    apply: 'build',
    configResolved(config) {
      // 捕获 **resolve 后**的绝对 outDir（相对 `root` 解析，与 vite 自身口径一致）。
      outDir = resolve(config.root, config.build.outDir);
    },
    writeBundle() {
      const skipped: string[] = [];
      copyTree(RUNTIME_ASSETS_ROOT, join(outDir, 'assets'), skipped);
      if (skipped.length > 0) {
        this.warn(`fu007-emit-runtime-assets: 跳过 ${skipped.length} 个非常规条目（非普通文件/目录）：${skipped.join(', ')}`);
      }
    },
  };
}

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
  plugins: [emitRuntimeAssets()],
  build: {
    outDir: '../../../.build/web',
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: true,
    // FU-007：打包产物与运行时资产分属不相交子树（见文件头说明）。
    assetsDir: 'assets/_bundle',
  },
});
