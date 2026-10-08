#!/usr/bin/env node
/**
 * `AC-F-2a` / `AC-F-2b` / `AC-F-2c` 的机器判据：**权威写入面**的 AST 扫描。
 *
 * 运行（workdir 写死 = `<ws>/v0/02_source/v0_skeleton/web`）：
 *   node <ws>/v0/spikes/n5-asset/authority_scan.mjs --root src [--inject <file> --needle <s> --replacement <s>]
 *
 * 判据：
 *   F-2a  「上行调用点集合」== 冻结清单：全树对**唯一上行 API**（`RenderClient.submitIntent`）
 *         的调用点，集合必须与 `assert_inputs.json` 的冻结清单**逐项相同**（多了 = 新开了上行面；
 *         少了 = 上行面被改道）。
 *   F-2b  「权威容器**只**由 `apply(message)` 赋值」：`presentation.ts` 的模块私有 `authority`
 *         对象的**赋值点集合** + 对 `applyAuthority(` 的调用点集合 == `{apply}`。
 *   F-2c  负对照（`--inject`）：在 `/tmp` 副本上往 `presentation.ts` 的表现层函数里加一行
 *         对权威容器的写 ⇒ 本工具**必红**。
 *
 * 建 AST 用 **TypeScript Compiler API**（盘上共享 `node_modules/typescript`）。
 * 本工具**只读**交付源码：`--inject` 一律在 `/tmp` 副本上做。
 */

import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, resolve } from 'node:path';

import ts from 'typescript';

const UPLINK_API = 'submitIntent';
const AUTHORITY_CONTAINER = 'authority';
const AUTHORITY_WRITER = 'apply';
const MUTATORS = new Set(['clear', 'set', 'push', 'delete', 'add', 'sort', 'splice', 'unshift']);

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, out);
    else if (/\.(ts|tsx|mts)$/.test(name) && !name.endsWith('.d.ts')) out.push(full);
  }
  return out;
}

function lineOf(source, node) {
  return source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
}

/** 收集：① `x.submitIntent(...)` 调用点；② 对 `authority.*` 的写入点（含**所属函数名**）；③ `apply(` 调用点。 */
export function scanFile(file, sourceText) {
  const source = ts.createSourceFile(file, sourceText, ts.ScriptTarget.ESNext, true, ts.ScriptKind.TS);
  const uplink = [];
  const authorityWrites = [];
  const writerCalls = [];

  function calleeText(node) {
    const expr = node.expression;
    if (ts.isPropertyAccessExpression(expr)) return expr.name.getText(source);
    if (ts.isIdentifier(expr)) return expr.getText(source);
    return '';
  }

  let fnStack = ['<module>'];

  function enclosing() {
    return fnStack[fnStack.length - 1];
  }

  function pushWrite(node, target) {
    authorityWrites.push({ file, line: lineOf(source, node), target, enclosing_function: enclosing() });
  }

  function visit(node) {
    const isFn = ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node)
      || ts.isArrowFunction(node) || ts.isFunctionExpression(node);
    if (isFn) {
      const name = node.name && ts.isIdentifier(node.name) ? node.name.text
        : (ts.isVariableDeclaration(node.parent) && ts.isIdentifier(node.parent.name) ? node.parent.name.text
          : '<anonymous>');
      fnStack.push(name);
    }
    if (ts.isCallExpression(node)) {
      const expr = node.expression;
      const name = calleeText(node);
      if (name === UPLINK_API && ts.isPropertyAccessExpression(expr)) {
        uplink.push({ file, line: lineOf(source, node), call: name });
      }
      // 唯一写者：**裸标识符** `apply(`（不是 `scene.apply(`）
      if (name === AUTHORITY_WRITER && ts.isIdentifier(expr)) {
        writerCalls.push({ file, line: lineOf(source, node), call: name, enclosing_function: enclosing() });
      }
      // 变更式写法：`authority.<prop>.<mutator>(...)`
      if (ts.isPropertyAccessExpression(expr) && MUTATORS.has(name)
          && ts.isPropertyAccessExpression(expr.expression)
          && ts.isIdentifier(expr.expression.expression)
          && expr.expression.expression.text === AUTHORITY_CONTAINER) {
        pushWrite(node, expr.getText(source));
      }
    }
    // 赋值：`authority.<prop> = ...` 或 `authority = ...`
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
      const lhs = node.left;
      if (ts.isPropertyAccessExpression(lhs) && ts.isIdentifier(lhs.expression)
          && lhs.expression.text === AUTHORITY_CONTAINER) {
        pushWrite(node, lhs.getText(source));
      }
      if (ts.isIdentifier(lhs) && lhs.text === AUTHORITY_CONTAINER) {
        pushWrite(node, AUTHORITY_CONTAINER);
      }
    }
    ts.forEachChild(node, visit);
    if (isFn) fnStack.pop();
  }
  visit(source);
  return { uplink, authorityWrites, writerCalls };
}

function scanRoot(root, label = '') {
  const files = walk(root);
  const uplink = [];
  const authorityWrites = [];
  const writerCalls = [];
  for (const f of files) {
    const text = readFileSync(f, 'utf8');
    const r = scanFile(f, text);
    const rel = label ? join(label, relative(root, f)) : f;
    uplink.push(...r.uplink.map((x) => ({ ...x, file: rel })));
    authorityWrites.push(...r.authorityWrites.map((x) => ({ ...x, file: rel })));
    writerCalls.push(...r.writerCalls.map((x) => ({ ...x, file: rel })));
  }
  return { uplink, authorityWrites, writerCalls, fileCount: files.length };
}

/** 判定：**所有**权威写入点必须落在 `apply` 函数体内。 */
function evaluate(result) {
  const problems = [];
  const writeFiles = [...new Set(result.authorityWrites.map((w) => w.file))];
  if (writeFiles.length > 1) {
    problems.push(`F-2b: 权威容器在 ${writeFiles.length} 个文件里被写：${writeFiles.join(', ')}`);
  }
  if (result.authorityWrites.length === 0) {
    problems.push('F-2b: 未找到权威容器写入点（锚失效 ⇒ 判据无牙）');
  }
  const outside = result.authorityWrites.filter((w) => w.enclosing_function !== AUTHORITY_WRITER);
  if (outside.length > 0) {
    problems.push(`F-2b: 权威写入点不在 \`${AUTHORITY_WRITER}\` 内：`
      + outside.map((w) => `${w.file}:${w.line}(${w.enclosing_function})`).join(', '));
  }
  const writerFiles = [...new Set(result.writerCalls.map((c) => c.file))];
  if (writerFiles.length > 1) {
    problems.push(`F-2b: \`${AUTHORITY_WRITER}(\` 被多个文件调用：${writerFiles.join(', ')}`);
  }
  return problems;
}

function main() {
  const argv = process.argv.slice(2);
  const get = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
  const rootArg = get('--root', 'src');
  const root = resolve(process.cwd(), rootArg);

  const result = scanRoot(root, rootArg);
  const problems = evaluate(result);

  // --- N5-r3 / A5（N-3 关闭）：`assert_inputs.json.f2a_frozen_uplink_call_sites` 的**真消费者**。
  // r2 的缺陷（raven N-3）：§19b 印着 `(F-2a)`，但该冻结清单**全仓 0 消费者** ——
  // `uplink_call_site_count` 只被打印、从未与冻结值比对 ⇒「新增一处上行调用点」这类回归不会变红。
  // 现在 `--frozen <assert_inputs.json>` 逐项比对（集合相等，不是计数）。
  const frozenArg = get('--frozen', null);
  let frozenComparison = null;
  if (frozenArg) {
    const frozenPath = resolve(process.cwd(), frozenArg);
    let expected = null;
    try {
      const frozen = JSON.parse(readFileSync(frozenPath, 'utf8'));
      const candidate = frozen.f2a_frozen_uplink_call_sites
        ?? (frozen.checks ? frozen.checks.f2a_frozen_uplink_call_sites : undefined);
      if (Array.isArray(candidate)) expected = candidate;
    } catch {
      expected = null;
    }
    const actualKeys = result.uplink.map((x) => `${x.file}:${x.line}:${x.call}`).sort();
    if (expected === null) {
      problems.push(`F-2a: 冻结清单不可读或缺失（${frozenPath}）`);
      frozenComparison = { frozen: frozenPath, expected: null, actual: actualKeys, mismatch: 'unreadable' };
    } else {
      const expectedKeys = expected.map((x) => `${x.file}:${x.line}:${x.call}`).sort();
      const missing = expectedKeys.filter((k) => !actualKeys.includes(k));
      const extra = actualKeys.filter((k) => !expectedKeys.includes(k));
      frozenComparison = {
        frozen: frozenPath, expected_count: expectedKeys.length, actual_count: actualKeys.length,
        expected: expectedKeys, actual: actualKeys, missing, extra, mismatch: missing.length + extra.length,
      };
      if (missing.length > 0 || extra.length > 0) {
        problems.push(`F-2a: 上行调用点集合 != 冻结清单（missing=${JSON.stringify(missing)} extra=${JSON.stringify(extra)}）`);
      }
    }
  }

  const report = {
    schema_version: 'n5-authority-scan/1',
    root: rootArg,
    file_count: result.fileCount,
    uplink_call_sites: result.uplink,
    uplink_call_site_count: result.uplink.length,
    authority_write_sites: result.authorityWrites,
    authority_write_file_count: new Set(result.authorityWrites.map((w) => w.file)).size,
    authority_writer_calls: result.writerCalls,
    /** N5-r3 / A5：`--frozen` 的比对结果（`mismatch === 0` 才是 F-2a 通过；`null` = 未提供冻结清单）。 */
    f2a_frozen_comparison: frozenComparison,
    problems,
  };

  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);

  // --- 负对照（F-2c）：/tmp 副本注入一行权威写 ⇒ 必红 ---
  const injectIdx = argv.indexOf('--inject');
  if (injectIdx >= 0) {
    const target = get('--inject');
    const tmp = mkdtempSync(join(tmpdir(), 'n5-auth-'));
    const copyRoot = join(tmp, rootArg);
    copyTree(root, copyRoot);
    const rel = relative(root, resolve(target));
    const file = join(copyRoot, rel);
    const original = readFileSync(file, 'utf8');
    const needle = get('--needle', 'step(dtMs: number) {');
    const replacement = get('--replacement', 'step(dtMs: number) {\n      authority.tick = 999; // INJECTED');
    if (!original.includes(needle)) {
      process.stdout.write(`negative_control: SKIPPED (needle not found: ${needle})\n`);
      rmSync(tmp, { recursive: true, force: true });
      process.exit(2);
    }
    writeFileSync(file, original.replace(needle, replacement), 'utf8');
    const injected = scanRoot(copyRoot, `${rootArg}(injected)`);
    const injectedProblems = evaluate(injected);
    const red = injected.authorityWrites.length > result.authorityWrites.length;
    process.stdout.write(`negative_control(inject ${rel}): ${red ? 'RED(期望)' : 'GREEN(异常！)'} `
      + `writes ${result.authorityWrites.length} -> ${injected.authorityWrites.length}, problems ${problems.length} -> ${injectedProblems.length}\n`);
    rmSync(tmp, { recursive: true, force: true });
    process.exit(red && problems.length === 0 ? 0 : 1);
  }

  if (problems.length > 0) {
    process.stdout.write(`authority_scan: FAILED\n`);
    for (const p of problems) process.stdout.write(`  - ${p}\n`);
    process.exit(1);
  }
  process.stdout.write(`authority_scan: OK（上行调用点 ${result.uplink.length} 处；权威写点 ${result.authorityWrites.length} 处，全在 presentation.ts）\n`);
  process.exit(0);
}

function copyTree(from, to) {
  mkdirSync(to, { recursive: true });
  for (const name of readdirSync(from)) {
    const src = join(from, name);
    const dst = join(to, name);
    if (statSync(src).isDirectory()) copyTree(src, dst);
    else writeFileSync(dst, readFileSync(src));
  }
}

if (import.meta.url === `file://${process.argv[1]}`) main();
