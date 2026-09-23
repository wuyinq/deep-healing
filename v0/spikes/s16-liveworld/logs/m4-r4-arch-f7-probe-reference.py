#!/usr/bin/env python3
"""architect 独立复现 F7：4 个「连接建立即关」的 churn 观察者 vs 0 观察者。

口径（与 .architect-verdict-m4-r3.md §4 一致）：
- 默认 ulimit -n（不得抬 RLIMIT_NOFILE）
- live --pace 0 --ticks 3000
- 4 个无间隔观察者，每次 connect 后立即关闭（accept churn）
- 采样 lsof -p <pid> | wc -l 峰值
输出：exit code / fd 峰值 / live_state.json 是否存在 / stderr 关键词
"""
import os, subprocess, sys, threading, time, socket, json, signal

WS = "/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-006-deephealing-v0-m4"
KERNEL = WS + "/02_source/v0_skeleton/kernel"
OUT = "/tmp/m4r4-archref"

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def run_arm(observers, tag):
    outdir = f"{OUT}/{tag}"
    os.makedirs(outdir, exist_ok=True)
    port = free_port()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "deephealing_kernel", "live",
           "--pack", "districts/xingfu-xiaoqu", "--seed", "20260921",
           "--out", outdir, "--port", str(port), "--pace", "0", "--ticks", "3000"]
    p = subprocess.Popen(cmd, cwd=KERNEL, env=env,
                         stdout=open(f"{OUT}/{tag}.out", "w"), stderr=open(f"{OUT}/{tag}.err", "w"))
    stop = threading.Event()
    peak = [0]; served = [0]

    def sampler():
        while not stop.is_set():
            try:
                n = len(subprocess.run(["lsof", "-p", str(p.pid)], capture_output=True, text=True).stdout.splitlines())
                peak[0] = max(peak[0], n)
            except Exception:
                pass
            time.sleep(0.05)

    def churn():
        while not stop.is_set():
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                s.sendall(b"GET /live/state HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
                s.recv(64); served[0] += 1
                s.close()          # 立即关闭 => accept churn
            except Exception:
                time.sleep(0.001)

    th = [threading.Thread(target=sampler, daemon=True)]
    for _ in range(observers):
        th.append(threading.Thread(target=churn, daemon=True))
    for t in th: t.start()
    t0 = time.time()
    rc = p.wait()
    wall = time.time() - t0
    stop.set(); time.sleep(0.2)
    err = open(f"{OUT}/{tag}.err").read()
    print(json.dumps({
        "tag": tag, "observers": observers, "exit": rc, "wall_s": round(wall, 2),
        "fd_peak": peak[0], "served_200ish": served[0],
        "live_state_json_exists": os.path.exists(f"{outdir}/live_state.json"),
        "errno24": "Too many open files" in err,
        "fatal_python_error": "Fatal Python error" in err,
        "summary_json_in_stdout": '"ticks"' in open(f"{OUT}/{tag}.out").read(),
    }, ensure_ascii=False))

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    run_arm(0, "obs0")
    for i in range(3):
        run_arm(4, f"obs4_run{i}")
