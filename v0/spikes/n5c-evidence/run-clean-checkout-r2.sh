#!/usr/bin/env bash
# N5-C r2 / FIX-4 · **干净检出五步（交付树副本形态）** + 取证隔离。
#
# 为什么不是 `git worktree add`：本轮**禁 commit** ⇒ `git worktree add <frozen-ref>` 只能检出
# **改动前**的基线（r1 的 E-1/E-5/E-6 正是这么红的，sentinel M-⑥ 已独立复核为「基线固有」）。
# 本轮唯一可行形态（任务书写死）：**交付树副本**（`02_source/**` 排除 `node_modules`/`.build`/
# `__pycache__`）⇒ 测的是**带本轮改动的干净检出**。
#
# 隔离（raven R-M3 的跨任务破坏）：`PLAYWRIGHT_BROWSERS_PATH` 指**独立目录** + `npm ci --ignore-scripts`
# ⇒ 不写共享 `~/Library/Caches/ms-playwright`、不触发 playwright 的浏览器下载 postinstall。
set -u
WS="/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/_worktrees/n5c-evidence-20260924"
SRC="$WS/v0/02_source"
DEST="/tmp/n5c-clean-r2"
LOG="$WS/v0/spikes/n5c-evidence/readback/clean-checkout-n5c-r2.log"
PLAYWRIGHT_CACHE="$HOME/Library/Caches/ms-playwright"
ISOLATED_BROWSERS="/tmp/n5c-pw-browsers-r2"
: > "$LOG"

step() {  # step <名称> <workdir> <命令...>
  local name="$1" wd="$2"; shift 2
  printf '\n=== STEP %s\nworkdir: %s\ncmd: %s\n' "$name" "$wd" "$*" >> "$LOG"
  ( cd "$wd" && "$@" ) >> "$LOG" 2>&1
  local rc=$?
  printf 'exit: %s\n' "$rc" >> "$LOG"
  printf 'STEP %s exit=%s\n' "$name" "$rc"
  return $rc
}

echo "--- 0) 共享浏览器缓存的**跑前**指纹（跑后必须逐字相同） ---" | tee -a "$LOG"
CACHE_BEFORE="$(ls -1 "$PLAYWRIGHT_CACHE" 2>/dev/null | sort | tr '\n' ' ')"
printf 'shared_cache_before=%s\n' "$CACHE_BEFORE" | tee -a "$LOG"

echo "--- 1) 检出副本（v0/** 排除 node_modules/.build/__pycache__ 与大体量取证产物） ---" | tee -a "$LOG"
rm -rf "$DEST" 2>/dev/null
mkdir -p "$DEST/v0"
rsync -a --exclude node_modules --exclude .build --exclude __pycache__ --exclude '.DS_Store' \
  --exclude 'spikes/*/runtime' --exclude 'spikes/n5-asset/shots' --exclude 'spikes/n5c-evidence/runtime' \
  --exclude 'out' \
  "$WS/v0"/ "$DEST/v0/" >> "$LOG" 2>&1
printf 'copied_files=%s\n' "$(find "$DEST/v0/02_source" -type f | wc -l | tr -d ' ')" | tee -a "$LOG"
printf 'node_modules_in_copy=%s (必须为 0)\n' "$(find "$DEST/v0/02_source" -name node_modules | wc -l | tr -d ' ')" | tee -a "$LOG"
printf 'lockfiles_in_copy=%s\n' "$(find "$DEST/v0/02_source" -name package-lock.json | wc -l | tr -d ' ')" | tee -a "$LOG"

WD="$DEST/v0/02_source/v0_skeleton"
mkdir -p "$ISOLATED_BROWSERS"
export PLAYWRIGHT_BROWSERS_PATH="$ISOLATED_BROWSERS"
printf 'PLAYWRIGHT_BROWSERS_PATH=%s\n' "$PLAYWRIGHT_BROWSERS_PATH" | tee -a "$LOG"

echo "--- 2a) 检出树（未装依赖）上的门禁：verify_specs 必须 FAIL==0 ---" | tee -a "$LOG"
step "verify_specs_preinstall" "$DEST/v0/02_source" bash verify_specs.sh --quiet

echo "--- 2b) npm ci（两个包；--ignore-scripts ⇒ 不跑 playwright 下载） ---" | tee -a "$LOG"
for pkg in web session; do
  step "npm_ci_$pkg" "$WD/$pkg" npm ci --ignore-scripts --no-audit --no-fund
done
# **依赖必须装在检出树之外**：真树上依赖位于**工作区根**（不在 `02_source` 内），
# 而 `verify_specs.sh` 的 7e) 残渣判据 `find . -name node_modules` 会把 `02_source` 内的
# `node_modules` 判红 —— 两者只有「装在树外」时才能同时成立。⇒ 把装好的树移出 `02_source`。
mv "$WD/web/node_modules" "$DEST/node_modules"
mv "$WD/session/node_modules" "$DEST/session-node_modules"
printf 'deps_relocated_to=%s (02_source 内残留 = %s)\n' "$DEST/node_modules" \
  "$(cd "$DEST/v0/02_source" && /usr/bin/find . \( -name node_modules -o -name dist -o -name .build \) | wc -l | tr -d ' ')" | tee -a "$LOG"

echo "--- 3) 构建 ---" | tee -a "$LOG"
step "build_web" "$WD/web" npm run build
printf 'build_output_dir=%s\n' "$(ls -d "$DEST/v0/.build/web" 2>/dev/null || echo MISSING)" | tee -a "$LOG"

echo "--- 4) 门禁（副本上） ---" | tee -a "$LOG"
step "verify_specs" "$DEST/v0/02_source" bash verify_specs.sh --quiet
step "scene_assert" "$WD/web" node scripts/scene_assert.mjs
step "render_client" "$WD/web" node --test test/render-client.test.ts

echo "--- 5) 共享浏览器缓存**跑后**指纹 ---" | tee -a "$LOG"
CACHE_AFTER="$(ls -1 "$PLAYWRIGHT_CACHE" 2>/dev/null | sort | tr '\n' ' ')"
printf 'shared_cache_after=%s\n' "$CACHE_AFTER" | tee -a "$LOG"
if [ "$CACHE_BEFORE" = "$CACHE_AFTER" ]; then
  printf 'shared_cache_unchanged=true\n' | tee -a "$LOG"
else
  printf 'shared_cache_unchanged=false  <-- 隔离失败\n' | tee -a "$LOG"
fi
printf 'isolated_browsers_dir=%s entries=%s\n' "$ISOLATED_BROWSERS" \
  "$(ls -1 "$ISOLATED_BROWSERS" 2>/dev/null | wc -l | tr -d ' ')" | tee -a "$LOG"
