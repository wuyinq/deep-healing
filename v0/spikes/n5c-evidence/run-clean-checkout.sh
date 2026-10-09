#!/usr/bin/env bash
# AC-E-1/E-5/E-6/E-7 · **干净检出**五步（`git worktree add`，无 node_modules 符号链接）。
# 逐步记录命令 + workdir + exit；不写本仓库的任何跟踪文件。
set -u
REPO="/Users/wooyinq/personal/deep-healing"
FROZEN="0fce37171a5ab2d67e083985d0f0e28a26da416b"
DEST="/tmp/n5c-clean"
LOG="/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/_worktrees/n5c-evidence-20260924/v0/spikes/n5c-evidence/readback/clean-checkout-n5c.log"
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

echo "--- 0) 清理旧目标 ---" | tee -a "$LOG"
rm -rf "$DEST" 2>/dev/null
git -C "$REPO" worktree prune >> "$LOG" 2>&1

echo "--- 1) git worktree add（干净检出，无符号链接） ---" | tee -a "$LOG"
git -C "$REPO" worktree add --detach "$DEST" "$FROZEN" >> "$LOG" 2>&1
echo "STEP worktree_add exit=$?" | tee -a "$LOG"
ls -la "$DEST" | head -12 >> "$LOG" 2>&1
printf 'node_modules_is_symlink=%s\n' "$([ -L "$DEST/node_modules" ] && echo yes || echo no)" | tee -a "$LOG"

WD="$DEST/v0/02_source/v0_skeleton"
for pkg in web session; do
  step "npm_ci_$pkg" "$WD/$pkg" npm ci --no-audit --no-fund
  echo "npm_ci_$pkg rc=$?" | tee -a "$LOG"
  step "npm_install_$pkg" "$WD/$pkg" npm install --no-audit --no-fund
  echo "npm_install_$pkg rc=$?" | tee -a "$LOG"
done

step "playwright_install_chromium" "$WD/web" npx playwright install chromium
echo "playwright rc=$?" | tee -a "$LOG"

step "build_web" "$WD/web" npm run build
echo "build rc=$?" | tee -a "$LOG"
printf 'build_output_dir=%s\n' "$(ls -d "$DEST/v0/.build/web" 2>/dev/null || echo MISSING)" | tee -a "$LOG"

echo "--- 5) 验收：三门禁 ---" | tee -a "$LOG"
step "verify_specs" "$DEST/v0/02_source" bash verify_specs.sh
step "scene_assert" "$WD/web" node scripts/scene_assert.mjs
step "render_client" "$WD/web" node --test test/render-client.test.ts

echo "--- 汇总 ---" | tee -a "$LOG"
grep -E "^STEP |^npm_ci_|^npm_install_|^playwright rc=|^build rc=|^node_modules_is_symlink=|^build_output_dir=" "$LOG" | tee -a "$LOG"
