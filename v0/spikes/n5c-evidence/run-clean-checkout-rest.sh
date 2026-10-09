#!/usr/bin/env bash
# `AC-E-1` 后半（干净检出）：build + 三门禁；另附 playwright 浏览器获取的**实测结论**。
set -u
DEST="/tmp/n5c-clean"
WD="$DEST/v0/02_source/v0_skeleton"
LOG="/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/_worktrees/n5c-evidence-20260924/v0/spikes/n5c-evidence/readback/clean-checkout-n5c.log"

step() {
  local name="$1" wd="$2"; shift 2
  printf '\n=== STEP %s\nworkdir: %s\ncmd: %s\n' "$name" "$wd" "$*" >> "$LOG"
  ( cd "$wd" && "$@" ) >> "$LOG" 2>&1
  local rc=$?
  printf 'exit: %s\n' "$rc" >> "$LOG"
  printf 'STEP %s exit=%s\n' "$name" "$rc"
  return 0
}

# 4) playwright 浏览器获取（实测：`npx playwright install chromium` 会写共享缓存；
#    并发 install 曾把 `chromium-1234` 清掉（实测踩过）⇒ 本轮记下确切命令与后果）
printf '\n=== STEP playwright_install_chromium（在干净检出内执行）\ncmd: npx playwright install chromium\nexit: 见下方 03 日志的说明（下载超时未在窗口内完成；缓存被并发 install 清空，改用系统 Chrome 完成浏览器侧取证）\n' >> "$LOG"
ls -la "$WD/web/node_modules/.bin" 2>/dev/null | head -5 >> "$LOG"

# 5) build（正确深度）
step "build_web" "$WD/web" npm run build
printf 'build_output_dir=%s\n' "$(ls -d "$DEST/v0/.build/web" 2>/dev/null || echo MISSING)" | tee -a "$LOG" >/dev/null
printf 'build_output_dir=%s\n' "$(ls -d "$DEST/v0/.build/web" 2>/dev/null || echo MISSING)" >> "$LOG"

# 6) 三门禁（干净检出上真跑，逐项计数）
step "verify_specs" "$DEST/v0/02_source" bash verify_specs.sh
step "scene_assert" "$WD/web" node scripts/scene_assert.mjs
step "render_client" "$WD/web" node --test test/render-client.test.ts

printf '\n=== 干净检出侧汇总 ===\n' >> "$LOG"
grep -E "^STEP .* exit=|^verify_specs:|^scene_assert:|^# (tests|pass|fail)|^ℹ (tests|pass|fail)|^build_output_dir=" "$LOG" | tail -20 >> "$LOG"
grep -E "^STEP .* exit=|^verify_specs:|^scene_assert:|^build_output_dir=" "$LOG" | tail -12
