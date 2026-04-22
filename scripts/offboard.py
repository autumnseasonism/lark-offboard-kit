#!/usr/bin/env python3
"""lark-offboard-kit — 员工离职交接包采集器

并行采集 5 模块 (docs / approval / im / task / calendar) → 渲染 Markdown + JSON
→ 可选一键转移动作。纯 stdlib，含模块级熔断 + 全局超时 + 限流退避。

用法:
  python3 offboard.py run --subject <uid> [--receiver <uid>] [--mode self|audit] [--out ./out/]
  python3 offboard.py handover --plan ./out/plan.json [--receiver <uid>] [--execute]
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Awaitable

IS_WIN = platform.system() == "Windows"

# ---------- 配置 ----------
GLOBAL_TIMEOUT_S     = 120
MODULE_TIMEOUT_S     = 30
MODULE_MAX_FAILURES  = 3
RATE_LIMIT_RETRIES   = 3

# ---------- 熔断器 ----------
@dataclass
class Breaker:
    name: str
    failures: int = 0
    tripped: bool = False
    reason: str = ""

    def record_fail(self, err: str) -> None:
        self.failures += 1
        if self.failures >= MODULE_MAX_FAILURES:
            self.tripped = True
            self.reason = f"连续 {self.failures} 次失败: {err[:120]}"

# ---------- 采集结果 ----------
@dataclass
class ModuleResult:
    module: str
    status: str = "ok"          # ok | partial | broken
    items: list = field(default_factory=list)
    note: str = ""
    scope_missing: bool = False

# ---------- CLI subprocess with 429 退避 ----------
async def _spawn(args: list[str]) -> asyncio.subprocess.Process:
    """Windows 上 npm 全局安装的 lark-cli 是 .cmd 包装，需走 shell 才能解析 PATHEXT。"""
    if IS_WIN:
        cmdline = subprocess.list2cmdline(args)
        return await asyncio.create_subprocess_shell(
            cmdline,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    return await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

async def run_cli(args: list[str], timeout: int = MODULE_TIMEOUT_S) -> tuple[int, str, str]:
    delay = 1.0
    last_err = ""
    for _ in range(RATE_LIMIT_RETRIES):
        try:
            proc = await _spawn(args)
        except FileNotFoundError:
            return 127, "", "lark-cli not found"
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return 124, "", "timeout"
        out = stdout.decode("utf-8", "replace")
        err = stderr.decode("utf-8", "replace")
        if proc.returncode == 0:
            return 0, out, err
        last_err = err or out
        low = last_err.lower()
        if "429" in last_err or "rate" in low or "too many" in low:
            await asyncio.sleep(delay)
            delay *= 2
            continue
        return proc.returncode, out, err
    return 429, "", f"rate limited after {RATE_LIMIT_RETRIES} retries: {last_err[:120]}"

def _scope_missing(err: str) -> bool:
    low = err.lower()
    return any(k in low for k in ("scope", "permission", "403", "unauthorized", "access denied"))

def _parse_json(text: str) -> Any:
    try:
        return json.loads(text) if text.strip() else None
    except json.JSONDecodeError:
        return None

def _unwrap(raw: Any) -> dict:
    """统一剥壳:
    - 原生 API: {code, data: {items, ...}, msg}
    - shortcut: {ok, data: <dict|list>, meta, _notice}
    - 若 data 是 list (日历事件等)，归一到 {items: [...]}。
    """
    if not isinstance(raw, dict):
        return {"items": raw} if isinstance(raw, list) else {}
    if "data" in raw:
        d = raw["data"]
        if isinstance(d, dict):
            return d
        if isinstance(d, list):
            return {"items": d}
    return raw

# ---------- 5 个模块采集器 ----------
# 命令均取自 lark-cli 1.0.15 实测签名 (见 references/cli-commands.md)

async def collect_docs(subject: str, br: Breaker, mode: str = "self",
                       query: str = "") -> ModuleResult:
    """docs +search 无 owner 过滤参数，query 必填；按关键词搜索 + 本地过滤"""
    if not query:
        return ModuleResult("docs", "partial",
                            note="需要 --query 关键词；可多次运行传入不同关键词聚合结果")
    rc, out, err = await run_cli([
        "lark-cli", "docs", "+search",
        "--query", query, "--page-size", "20", "--format", "json"
    ])
    if rc != 0:
        br.record_fail(err)
        return ModuleResult("docs", "broken", note=err.strip()[:200] or f"rc={rc}",
                            scope_missing=_scope_missing(err))
    data = _unwrap(_parse_json(out))
    items = (data.get("items") or
             (data.get("doc_wiki") or {}).get("items") or [])
    # 有 owner_id 字段时过滤到 subject；否则保留全部，标 partial
    filtered, all_have_owner = [], True
    for it in items:
        if not isinstance(it, dict):
            continue
        owner = it.get("owner_id") or it.get("creator_id") or it.get("owner")
        if owner is None:
            all_have_owner = False
            filtered.append(it)
        elif owner == subject or mode == "self":
            filtered.append(it)
    return ModuleResult(
        "docs",
        "ok" if all_have_owner else "partial",
        items=[{"title": it.get("title") or it.get("doc_name") or "(未命名)",
                "token": it.get("token") or it.get("doc_token") or it.get("object_token"),
                "url": it.get("url") or it.get("link")}
               for it in filtered],
        note=(f"按关键词 '{query}' 搜索，返回 {len(items)} 项"
              + ("" if all_have_owner else "；部分项无 owner 字段已全部保留，需人工复核"))
    )

async def collect_approval(subject: str, br: Breaker, mode: str = "self") -> ModuleResult:
    """approval tasks query 只查登录用户的待办；audit 模式需切换到 raw api (暂未实现)"""
    if mode == "audit":
        return ModuleResult("approval", "broken",
                            note="audit 模式需 tenant 级审批实例 API，当前仅支持 self 模式",
                            scope_missing=True)
    # schema: topic=1 (待办), topic=2 (已办)，页分参数走 --params JSON
    rc, out, err = await run_cli([
        "lark-cli", "approval", "tasks", "query",
        "--params", '{"topic":"1","page_size":"100"}',
        "--page-all", "--format", "json"
    ])
    if rc != 0:
        br.record_fail(err)
        return ModuleResult("approval", "broken", note=err.strip()[:200] or f"rc={rc}",
                            scope_missing=_scope_missing(err))
    data = _unwrap(_parse_json(out))
    tasks = data.get("task_list") or data.get("tasks") or data.get("items") or []
    return ModuleResult("approval", "ok", items=[
        {"task_id": t.get("id") or t.get("task_id"),
         "instance_code": t.get("instance_code"),
         "definition": t.get("approval_name") or t.get("definition_name") or "(未知审批)"}
        for t in tasks if isinstance(t, dict)
    ])

async def collect_chats(subject: str, br: Breaker, mode: str = "self") -> ModuleResult:
    """im chats list — 列出登录用户加入的全部群，本地过滤 owner_id == subject"""
    args = ["lark-cli", "im", "chats", "list",
            "--params", '{"page_size":"100"}',
            "--page-all", "--format", "json"]
    rc, out, err = await run_cli(args, timeout=45)
    if rc != 0:
        br.record_fail(err)
        return ModuleResult("chat_owner", "broken", note=err.strip()[:200] or f"rc={rc}",
                            scope_missing=_scope_missing(err))
    data = _unwrap(_parse_json(out))
    raw = data.get("items") or data.get("chats") or []
    chats = [c for c in raw if isinstance(c, dict) and c.get("owner_id") == subject]
    partial = len(raw) >= 100
    return ModuleResult(
        "chat_owner", "partial" if partial else "ok",
        items=[{"chat_id": c.get("chat_id"), "name": c.get("name")}
               for c in chats if isinstance(c, dict)],
        note=("结果达分页上限 100，建议 App 内自助补全" if partial else ""),
    )

async def collect_tasks(subject: str, br: Breaker, mode: str = "self") -> ModuleResult:
    """task: self 用 +get-my-tasks, audit 用 +search --assignee"""
    if mode == "self":
        args = ["lark-cli", "task", "+get-my-tasks",
                "--complete=false", "--page-all", "--format", "json"]
    else:
        args = ["lark-cli", "task", "+search",
                "--assignee", subject, "--completed=false",
                "--page-all", "--format", "json"]
    rc, out, err = await run_cli(args)
    if rc != 0:
        br.record_fail(err)
        return ModuleResult("tasks", "broken", note=err.strip()[:200] or f"rc={rc}",
                            scope_missing=_scope_missing(err))
    data = _unwrap(_parse_json(out))
    items = data.get("items") or data.get("tasks") or []
    return ModuleResult("tasks", "ok", items=[
        {"task_id": t.get("guid") or t.get("id"),
         "summary": t.get("summary") or "(无标题)",
         "due": (t.get("due") or {}).get("timestamp") if isinstance(t.get("due"), dict) else t.get("due")}
        for t in items if isinstance(t, dict)
    ])

async def collect_calendar(subject: str, br: Breaker, mode: str = "self") -> ModuleResult:
    """calendar +agenda 只读登录用户主日历；audit 需 raw api"""
    if mode == "audit":
        return ModuleResult("calendar", "broken",
                            note="audit 模式需他人 calendar-id 或 tenant 级日历 API，当前仅支持 self 模式",
                            scope_missing=True)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    start_iso = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    end_iso = (now + timedelta(days=14)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    rc, out, err = await run_cli([
        "lark-cli", "calendar", "+agenda",
        "--start", start_iso, "--end", end_iso, "--format", "json"
    ])
    if rc != 0:
        br.record_fail(err)
        return ModuleResult("calendar", "broken", note=err.strip()[:200] or f"rc={rc}",
                            scope_missing=_scope_missing(err))
    data = _unwrap(_parse_json(out))
    events = data.get("events") or data.get("items") or []
    # 周期事件标识：recurrence 非空 或 recurring_event_id 存在
    recurring = [e for e in events if isinstance(e, dict) and
                 (e.get("recurrence") or e.get("recurring_event_id"))]
    return ModuleResult("calendar", "ok", items=[
        {"event_id": e.get("event_id"),
         "summary": e.get("summary") or "(无主题)",
         "recurrence": e.get("recurrence") or e.get("recurring_event_id")}
        for e in recurring
    ])

# 预留扩展点（用户要求暂不计入联系人/客户模块）
# async def collect_contacts(subject, br): ...

MODULES: list[tuple[str, Callable[[str, Breaker], Awaitable[ModuleResult]]]] = [
    ("docs",       collect_docs),
    ("approval",   collect_approval),
    ("chat_owner", collect_chats),
    ("tasks",      collect_tasks),
    ("calendar",   collect_calendar),
]

# ---------- 编排 ----------
async def _guarded(name: str, fn, subject: str, br: Breaker,
                   mode: str, docs_query: str) -> ModuleResult:
    if br.tripped:
        return ModuleResult(name, "broken", note=f"熔断: {br.reason}")
    try:
        if name == "docs":
            return await fn(subject, br, mode=mode, query=docs_query)
        return await fn(subject, br, mode=mode)
    except TypeError:
        # 兼容旧签名 (测试 monkey-patch 用)
        return await fn(subject, br)
    except Exception as e:
        br.record_fail(str(e))
        return ModuleResult(name, "broken", note=f"异常: {e}")

async def collect_all(subject: str, scopes: dict | None = None,
                      mode: str = "self", docs_query: str = "") -> dict:
    breakers = {name: Breaker(name) for name, _ in MODULES}
    coros = []
    for name, fn in MODULES:
        if scopes and name in scopes and scopes[name].get("ok") is False:
            breakers[name].tripped = True
            breakers[name].reason = scopes[name].get("reason", "scope 探测失败")
        coros.append(_guarded(name, fn, subject, breakers[name], mode, docs_query))
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*coros, return_exceptions=False),
            timeout=GLOBAL_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        results = [ModuleResult(name, "broken", note="全局超时") for name, _ in MODULES]
    broken = sum(1 for r in results if r.status == "broken")
    return {
        "subject": subject,
        "mode": mode,
        "collected_at": int(time.time()),
        "modules": [asdict(r) for r in results],
        "summary": {
            "total_modules": len(results),
            "broken": broken,
            "warning": "≥3 模块失败，数据不完整，建议人工复核" if broken >= 3 else None,
        },
    }

# ---------- 渲染 ----------
_ICONS = {"ok": "✅", "partial": "⚠️", "broken": "❌"}
_TITLES = {
    "docs": "文档资产", "approval": "待处理审批", "chat_owner": "群主身份",
    "tasks": "未完成任务", "calendar": "周期会议",
}

def _fmt_item(mod: str, it: dict) -> str:
    if mod == "docs":
        t = it.get("title") or "(无标题)"
        u = it.get("url") or it.get("token", "")
        return f"- [{t}]({u})" if u.startswith("http") else f"- {t}  `{u}`"
    if mod == "approval":
        return f"- {it.get('definition','?')}  `{it.get('instance_code','')}`"
    if mod == "chat_owner":
        return f"- {it.get('name','(未命名群)')}  `{it.get('chat_id','')}`"
    if mod == "tasks":
        due = f"  截止: {it['due']}" if it.get("due") else ""
        return f"- {it.get('summary','?')}{due}  `{it.get('task_id','')}`"
    if mod == "calendar":
        return f"- {it.get('summary','?')}  `{it.get('event_id','')}`"
    return f"- {it}"

def render_markdown(plan: dict, receiver: str | None) -> str:
    ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(plan["collected_at"]))
    lines = [
        f"# 离职交接清单 — {plan['subject']}",
        "",
        f"- 生成时间：{ts}",
        f"- 接收人：{receiver or '_（待指定）_'}",
        "",
    ]
    warn = plan.get("summary", {}).get("warning")
    if warn:
        lines += [f"> ⚠️ **{warn}**", ""]
    for mod in plan["modules"]:
        name = mod["module"]
        icon = _ICONS.get(mod["status"], "❓")
        title = _TITLES.get(name, name)
        lines.append(f"\n## {icon} {title} — {len(mod['items'])} 项")
        if mod.get("note"):
            lines.append(f"> {mod['note']}")
        if mod.get("scope_missing"):
            lines.append(f"> ℹ️ scope 不足，建议当事人在 self 模式下重跑或由管理员补齐权限。")
        for it in mod["items"][:50]:
            lines.append(_fmt_item(name, it))
        if len(mod["items"]) > 50:
            lines.append(f"- _...还有 {len(mod['items']) - 50} 项，见 `plan.json`_")
    return "\n".join(lines) + "\n"

# ---------- 一键动作 ----------
def _build_actions(plan: dict, receiver: str) -> list[dict]:
    actions: list[dict] = []
    for mod in plan["modules"]:
        if mod["status"] == "broken":
            continue
        if mod["module"] == "chat_owner":
            for it in mod["items"]:
                actions.append({
                    "kind": "chat_transfer", "label": it.get("name", ""),
                    "cmd": ["lark-cli", "im", "+chat-update",
                            "--chat-id", it["chat_id"], "--owner", receiver],
                })
        elif mod["module"] == "tasks":
            for it in mod["items"]:
                actions.append({
                    "kind": "task_reassign", "label": it.get("summary", ""),
                    "cmd": ["lark-cli", "task", "+update",
                            "--task-id", it["task_id"], "--assignee", receiver],
                })
    return actions

def handover(plan: dict, receiver: str, execute: bool) -> int:
    actions = _build_actions(plan, receiver)
    print(f"\n=== 计划执行 {len(actions)} 项转移 → {receiver} ===\n")
    for a in actions:
        print(f"  [{a['kind']}] {a['label']}")
    if not actions:
        print("  (无可执行项)")
        return 0
    if not execute:
        print("\n(dry-run；加 --execute 真实执行)")
        return 0
    try:
        confirm = input("\n确认执行？[y/N] ").strip().lower()
    except EOFError:
        confirm = "n"
    if confirm != "y":
        print("已取消")
        return 0
    fails = 0
    for a in actions:
        r = subprocess.run(a["cmd"], capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  ✓ [{a['kind']}] {a['label']}")
        else:
            fails += 1
            print(f"  ✗ [{a['kind']}] {a['label']} — {r.stderr.strip()[:120]}")
    print(f"\n完成：成功 {len(actions)-fails} / 失败 {fails}")
    return 0 if fails == 0 else 2

# ---------- 可选：自动建飞书交接文档 ----------
def create_handover_doc(subject: str, markdown: str) -> str | None:
    try:
        r = subprocess.run(
            ["lark-cli", "docs", "+create",
             "--title", f"离职交接 - {subject}",
             "--markdown", markdown],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None

# ---------- CLI 入口 ----------
def _load_scopes() -> dict | None:
    p = Path(os.environ.get("OFFBOARD_CACHE_DIR", "./.offboard-cache")) / "scopes.json"
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            return None
    return None

def cmd_run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    scopes = _load_scopes()
    plan = asyncio.run(collect_all(args.subject, scopes,
                                    mode=args.mode,
                                    docs_query=args.docs_query or ""))
    plan["receiver"] = args.receiver

    (out_dir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = render_markdown(plan, args.receiver)
    md_path = out_dir / f"handover-{args.subject}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"✓ 交接清单: {md_path}")
    print(f"✓ 结构化数据: {out_dir / 'plan.json'}")

    if os.environ.get("OFFBOARD_CREATE_DOC") == "1":
        token = create_handover_doc(args.subject, md)
        if token:
            (out_dir / "handover.docx_token").write_text(token, encoding="utf-8")
            print(f"✓ 飞书文档已创建: {token}")
        else:
            print("✗ 飞书文档创建失败（可手动将 Markdown 上传）")

    broken = plan["summary"]["broken"]
    if broken:
        print(f"⚠️  {broken} 模块降级/熔断，详见清单", file=sys.stderr)
    return 0 if broken == 0 else 2

def cmd_handover(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.plan).read_text("utf-8"))
    receiver = args.receiver or plan.get("receiver")
    if not receiver:
        print("错误: 需要 --receiver 或 plan.json 里已包含 receiver", file=sys.stderr)
        return 1
    return handover(plan, receiver, args.execute)

def main() -> int:
    p = argparse.ArgumentParser(prog="offboard", description="lark-offboard-kit")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="采集 + 生成交接包")
    pr.add_argument("--subject",  required=True, help="员工 open_id 或邮箱")
    pr.add_argument("--receiver", help="交接接收人 open_id")
    pr.add_argument("--mode",     choices=["self", "audit"], default="self")
    pr.add_argument("--out",      default="./out")
    pr.add_argument("--docs-query", default="",
                    help="docs 搜索关键词（docs +search 需要 query；如团队/部门名/项目名）")

    ph = sub.add_parser("handover", help="执行一键转移（默认 dry-run）")
    ph.add_argument("--plan",     required=True, help="plan.json 路径")
    ph.add_argument("--receiver", help="覆盖 plan 里的 receiver")
    ph.add_argument("--execute",  action="store_true", help="真实执行（否则仅 dry-run）")

    args = p.parse_args()
    if args.cmd == "run":      return cmd_run(args)
    if args.cmd == "handover": return cmd_handover(args)
    return 1

if __name__ == "__main__":
    sys.exit(main())
