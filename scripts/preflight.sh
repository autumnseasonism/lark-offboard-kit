#!/usr/bin/env bash
# preflight — 检测/自动安装 lark-cli，验证登录，探测各模块 scope 可用性
# Exit codes: 0=ok, 1=install failed, 2=auth failed, 3=all probes failed
set -eo pipefail

CACHE_DIR="${OFFBOARD_CACHE_DIR:-./.offboard-cache}"
mkdir -p "$CACHE_DIR"

log() { printf '[preflight] %s\n' "$*" >&2; }

# ----------- 1) 检测 lark-cli -----------
if ! command -v lark-cli >/dev/null 2>&1; then
  log "lark-cli 未安装，尝试自动安装 (npm install -g @larksuite/cli)..."
  if command -v npm >/dev/null 2>&1; then
    if ! npm install -g @larksuite/cli 2>&1 | tail -20 >&2; then
      log "npm 自动安装失败，请手动执行："
      log "  npm install -g @larksuite/cli"
      log "  或源码: git clone https://github.com/larksuite/cli.git && cd cli && make install"
      exit 1
    fi
  else
    log "未检测到 npm。请先安装 Node.js 18+ 然后："
    log "  npm install -g @larksuite/cli"
    exit 1
  fi
fi
log "lark-cli: $(lark-cli --version 2>&1 | head -1)"

# ----------- 2) 检查登录状态 -----------
if ! lark-cli auth status >/dev/null 2>&1; then
  log "未登录或 token 已过期。请运行："
  log "  lark-cli config init        # 首次使用"
  log "  lark-cli auth login --recommend"
  exit 2
fi
log "已登录: $(lark-cli auth status 2>&1 | head -1)"

# ----------- 3) 探测各模块 scope 可用性 -----------
SCOPES_FILE="$CACHE_DIR/scopes.json"
log "探测 scope 可用性 (各模块轻量调用 1 次)..."

python3 - "$SCOPES_FILE" <<'PY'
import json, subprocess, sys, os

probes = {
    "docs":     ["lark-cli", "docs",     "+search",    "--query", "_probe_", "--page-size", "1"],
    "approval": ["lark-cli", "approval", "+query",     "--status", "PENDING", "--page-size", "1"],
    "im":       ["lark-cli", "im",       "+chat-list", "--page-size", "1"],
    "task":     ["lark-cli", "task",     "+query",     "--page-size", "1"],
    "calendar": ["lark-cli", "calendar", "+agenda",    "--days",    "1"],
}
out = {}
for name, cmd in probes.items():
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=15, text=True)
        ok = (r.returncode == 0)
        reason = "" if ok else (r.stderr or r.stdout).strip().splitlines()[-1][:200] if (r.stderr or r.stdout).strip() else f"rc={r.returncode}"
    except subprocess.TimeoutExpired:
        ok, reason = False, "timeout"
    except Exception as e:
        ok, reason = False, str(e)[:200]
    out[name] = {"ok": ok, "reason": reason}

with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

usable = sum(1 for v in out.values() if v["ok"])
print(json.dumps(out, ensure_ascii=False, indent=2), file=sys.stderr)
print(f"[preflight] 可用模块: {usable}/{len(out)}", file=sys.stderr)
sys.exit(0 if usable > 0 else 3)
PY

log "scope 探测写入 → $SCOPES_FILE"
log "完成。可以执行: python3 scripts/offboard.py run --subject <id> --out ./out/"
