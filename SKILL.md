---
name: lark-offboard-kit
version: 1.0.0
description: "员工离职交接包：输入员工 ID → 并行采集文档/审批/群主/任务/周期会议 5 类资产 → 生成交接清单 + 飞书交接文档 → 可选一键转群主/转任务/发起交接审批。支持员工自查(self) + HR 审计(audit) 双模式，带熔断降级。当用户提到离职、转岗、岗位变更、长假交接、员工 offboarding、资产梳理、权限回收、群主转让、任务交接、交接清单、某员工即将离开时，即使没有明确说'离职交接'也要使用此技能。"
metadata:
  requires:
    bins: ["lark-cli", "python3"]
---

# Lark Offboard Kit — 离职交接一站式工具

把原本分散在 5 个飞书模块里的"某员工资产梳理"动作合并成一条命令。生成可复核的交接清单 + 飞书交接文档，并提供一键转移动作（dry-run 默认）。

> **自包含声明**：本 skill 刻意不引用 `../lark-shared/SKILL.md`。认证/安装检测由 `scripts/preflight.sh` 内联完成——检测到 `lark-cli` 缺失会自动调 `npm install -g @larksuite/cli`，未登录则给出 `lark-cli auth login` 指引，scope 探测结果缓存到 `.offboard-cache/scopes.json`。单仓拷出即可独立运行。

## 设计目标

| 维度 | 做法 |
|---|---|
| **实用性** | 离职/转岗/长假刚需，HR + 本人都能用 |
| **整合力** | 单次运行聚合 docs / approval / im / task / calendar |
| **鲁棒性** | 模块级熔断 + 全局超时 + 限流指数退避 + 三档降级输出 |
| **自包含** | 纯 Python3 stdlib + bash，无 pip 依赖；lark-cli 缺失自动安装 |
| **闭环** | 不只是清单，还能一键转群主/任务、发起交接审批 |

## 快速开始

```bash
# 0) 前置检查（自动安装 lark-cli、验证登录、探测 scope）
bash scripts/preflight.sh

# 1) 采集 + 生成交接包
python3 scripts/offboard.py run \
  --subject     <离职员工 open_id 或邮箱> \
  --receiver    <接收人 open_id> \
  --mode        self \
  --docs-query  "项目名/部门名/关键词"   # docs +search 需 query 参数
  --out         ./out/

# 2) 查看交接清单
cat ./out/handover-<subject>.md

# 3) 一键转移（默认 dry-run，加 --execute 并交互确认才会执行）
python3 scripts/offboard.py handover --plan ./out/plan.json
python3 scripts/offboard.py handover --plan ./out/plan.json --execute
```

## 双模式

| 模式 | 运行者 | 采集范围 | scope 要求 |
|---|---|---|---|
| `self` | 员工本人 | 仅本人资产 | 基础 user scope |
| `audit` | HR/管理员 | 任意员工 | tenant 级 scope |

`preflight.sh` 会探测实际可用 scope 写入 `.offboard-cache/scopes.json`；scope 不足时 `offboard.py` 自动降级到 self 模式并在报告里标注。

## 5 个采集模块（基于 lark-cli 1.0.15 实测命令）

| # | 模块 | 真实命令 | 备注 |
|---|---|---|---|
| 1 | 文档资产 | `lark-cli docs +search --query <kw>` | `+search` 无 owner 过滤，需关键词检索后本地过滤；通过 `--docs-query` 传入 |
| 2 | 待处理审批 | `lark-cli approval tasks query --params '{"topic":"1",...}'` | `topic=1` 表示待办；只查登录用户自己，audit 需 raw api |
| 3 | 群主身份 | `lark-cli im chats list --page-all` + 本地 `owner_id==subject` | `+chat-search` 需 query，不适合枚举；`chats list` 更可靠 |
| 4 | 未完成任务 | self: `task +get-my-tasks --complete=false`<br>audit: `task +search --assignee $UID --completed=false` | 两种命令签名不同 |
| 5 | 周期会议 | `lark-cli calendar +agenda --start <ISO> --end <ISO>` | 只读登录用户主日历；按 `recurrence`/`recurring_event_id` 过滤周期事件 |

**响应剥壳**：原生 API 返回 `{code, data, msg}`，shortcut 返回 `{ok, data, meta}`，日历 shortcut 的 `data` 是裸 list — `_unwrap()` 函数统一处理三种形态。

> 联系人/客户模块按需求暂不计入。预留扩展点在 `collect_contacts` 空函数中。

## 熔断机制

- **模块级熔断**：单模块连续 3 次失败 → 熔断，跳过重试
- **限流退避**：429 响应 → 指数退避 1s → 2s → 4s，超 3 次熔断
- **全局超时**：120 秒 → 取消未完成模块，输出已采集部分
- **完整度告警**：≥3 模块熔断 → 报告顶部红色横幅
- **退出码**：0=全 ok / 2=部分降级 / 1=前置失败 / 3=认证失败

## 输出产物

1. `out/handover-<subject>-<date>.md` — 人类可读清单
2. `out/plan.json` — 结构化数据 + 待执行动作
3. `out/handover.docx_token` — 自动建的飞书交接文档（设 `OFFBOARD_CREATE_DOC=1`）

## 一键动作

| 动作 | 命令 |
|---|---|
| 转群主 | `lark-cli im +chat-update --chat-id X --owner <new>` |
| 转任务 | `lark-cli task +update --task-id X --assignee <new>` |
| 发起交接审批 | `lark-cli approval +create --definition-code <code> --form ...` |

默认 `dry-run`；加 `--execute` 后逐项交互确认执行。失败项独立计错，不中断整体。

## 权限 scope 速查

| 模块 | 读 | 写 |
|---|---|---|
| 文档 | `docs:document:readonly` | `docs:document` |
| 审批 | `approval:approval` | `approval:approval` |
| 群聊 | `im:chat:readonly` | `im:chat` |
| 任务 | `task:task` | `task:task` |
| 日历 | `calendar:calendar:readonly` | `calendar:calendar` |

完整版 → [`references/scopes.md`](references/scopes.md)
降级决策树 → [`references/degradation.md`](references/degradation.md)

## 目录结构

```
lark-offboard-kit/
├── SKILL.md
├── scripts/
│   ├── preflight.sh        # 检测 + 安装 + scope 探测
│   └── offboard.py         # 采集 + 渲染 + 一键动作（stdlib only）
└── references/
    ├── scopes.md
    └── degradation.md
```
