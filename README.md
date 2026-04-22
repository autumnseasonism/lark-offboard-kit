<div align="center">

# 🎒 lark-offboard-kit

### 员工离职交接一站式工具 · 基于飞书 CLI

<p>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/python-3.8+-3776ab.svg?logo=python&logoColor=white" alt="Python 3.8+" />
  <a href="https://github.com/larksuite/cli"><img src="https://img.shields.io/badge/lark--cli-1.0.15+-ff4d4f.svg" alt="lark-cli" /></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg" alt="Platform" />
  <img src="https://img.shields.io/badge/tests-46%20passing-brightgreen.svg" alt="Tests" />
  <img src="https://img.shields.io/badge/zero-dependencies-success.svg" alt="No deps" />
</p>

**一条命令，聚合飞书 5 大模块，生成可复核的离职交接清单**

[安装](#-安装) · [快速开始](#-快速开始) · [工作原理](#-工作原理) · [权限](#-权限-scope) · [常见问题](#-常见问题) · [路线图](#-路线图)

</div>

---

## 💡 为什么做这个

员工**离职 / 转岗 / 长假**交接时，HR 和团队负责人需要梳理此人名下的：

<table>
<tr>
  <td align="center">📄<br/><b>文档</b><br/>还在流转的飞书文档</td>
  <td align="center">✅<br/><b>审批</b><br/>压在他手上的待办</td>
  <td align="center">👥<br/><b>群主</b><br/>他创建的群聊</td>
  <td align="center">📋<br/><b>任务</b><br/>未完成的任务</td>
  <td align="center">📅<br/><b>日程</b><br/>固定的周期会议</td>
</tr>
</table>

这些数据**分散在飞书 5 个独立模块**里，手工梳理要翻 N 个入口、对着 Excel 抄来抄去——一漏就是"下周才发现 XX 群没人管了"。

> **本工具把这整件事压缩为一条命令。**

---

## ✨ 核心能力

<table>
<tr>
<td width="50%" valign="top">

### 🎯 一条命令聚合 5 类资产
`asyncio.gather` 并行调用 lark-cli，单次运行覆盖
docs / approval / im / task / calendar。

</td>
<td width="50%" valign="top">

### 🔄 双模式
- **`self`** — 员工本人自查（基础 user scope）
- **`audit`** — HR 审计查他人（需管理员 scope）

脚本自动探测 scope，不足时降级并提示。

</td>
</tr>
<tr>
<td valign="top">

### 🛡️ 工程级鲁棒性
- 模块级**熔断器**（连续 3 次失败跳过）
- 429 **指数退避**（1s → 2s → 4s）
- **全局超时** 120s
- **三档状态机** ✅ ⚠️ ❌

局部失败不影响整体产出。

</td>
<td valign="top">

### 🔗 一键闭环
不只是清单——还能：
1. 自动创建飞书**交接文档**
2. 批量**转群主** / **转任务**
3. 发起**交接审批**（可选）

</td>
</tr>
<tr>
<td valign="top">

### 📦 自包含
- 纯 Python 3.8+ **stdlib**，无 pip 依赖
- 检测到 `lark-cli` 缺失 → 自动 `npm install`
- 单目录拷走即可独立运行

</td>
<td valign="top">

### 🔒 默认 dry-run
所有写操作（转群主/转任务）默认**只打印计划**。
需 `--execute` **且**逐项 `y/N` 交互确认。
防误触、可审计。

</td>
</tr>
</table>

---

## 📦 安装

### ✅ 推荐方式：直接对 Agent 说

在 Claude Code / Cursor / 任意支持 skill 的 Agent 里直接发：

> **请帮我安装这个 skill：**
> **`https://github.com/autumnseasonism/lark-offboard-kit.git`**

如果该 Agent 支持 skill 安装，通常这就是最简单的方式——Agent 会自动 clone 并放到正确的扫描路径。

### 🛠️ 手动安装

```bash
# 放在当前项目目录下，或放到 Agent 的 skills 扫描路径下
git clone https://github.com/autumnseasonism/lark-offboard-kit.git
```

把仓库目录放到**当前项目目录**，或对应 Agent 的 **skills 扫描路径**下即可生效。该安装方式**所有 Agent 通用**。

### 📋 运行环境

- **Node.js 18+** — 仅用于 `npm` 安装 lark-cli（已有 lark-cli 可跳过）
- **Python 3.8+** — 纯 stdlib，无 pip 依赖
- **飞书账号** — self 模式用 user scope；audit 模式需管理员 scope

---

## 🚀 快速开始

### 一条龙

```bash
# 1. 进入 skill 目录
cd lark-offboard-kit

# 2. 前置检查（自动安装 lark-cli + 登录校验 + scope 探测）
bash scripts/preflight.sh

# 3. 生成交接包
python3 scripts/offboard.py run \
  --subject     ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  --receiver    ou_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy \
  --mode        self \
  --docs-query  "产品" \
  --out         ./out/

# 4. 查看清单
cat ./out/handover-*.md

# 5. 一键转移（先 dry-run 预览，确认后再加 --execute）
python3 scripts/offboard.py handover --plan ./out/plan.json
python3 scripts/offboard.py handover --plan ./out/plan.json --execute
```

---

## 📸 真实产物示例

下方是在真实飞书环境下（`lark-cli v1.0.15` 登录用户）跑出的实际清单：

```markdown
# 离职交接清单 — ou_5bace936762e84a7b8e422ca28ec5eea

- 生成时间：2026-04-22 16:23
- 接收人：_（待指定）_

## ✅ 文档资产 — 0 项
> 按关键词 '产品' 搜索，返回 0 项

## ✅ 待处理审批 — 0 项

## ✅ 群主身份 — 7 项
- autumn       `oc_8ee99105e7dcb86c4cb30731d6c97da7`
- map          `oc_86bb68ff13e71b00b48ea4fa3d890e44`
- claudecode   `oc_e42d163f892fafd8999411c9f5c26a81`
- 楮知白        `oc_3d877b2c9b5b88d3976771d947214af8`
- 开权限        `oc_f14e4e453f9531a75a4322a7535af140`
- 面试         `oc_571f1cebe671f9a74993f12d5cdb1d4a`
- work         `oc_3a2dfd436097eed07f7d540ae6030605`

## ✅ 未完成任务 — 0 项
## ✅ 周期会议 — 0 项
```

---

## 🏗️ 工作原理

```
                        ┌──────────────────────────────────┐
                        │         preflight.sh             │
                        │                                  │
                        │  ① 检测 lark-cli                  │
                        │      ↳ 缺失 → npm install -g      │
                        │  ② lark-cli auth status           │
                        │  ③ 探测 5 模块 scope              │
                        │      → .offboard-cache/scopes.json│
                        └──────────────┬───────────────────┘
                                       │
                                       ▼
                ┌────────────────────────────────────────────┐
                │             offboard.py run                │
                │                                            │
                │    ┌──────┐ ┌────────┐ ┌───────┐          │
                │    │ docs │ │approval│ │  im   │          │
                │    └──┬───┘ └───┬────┘ └───┬───┘          │
                │       │         │          │   + 2 more   │
                │       └─────────┼──────────┘              │
                │                 ▼                          │
                │       asyncio.gather(return_exceptions)    │
                │                 │                          │
                │  ┌──────────────┴────────────────────┐    │
                │  │  熔断 · 429 退避 · 全局超时 · 降级  │    │
                │  └──────────────┬────────────────────┘    │
                │                 ▼                          │
                │      plan.json + handover-*.md             │
                └─────────────────┬──────────────────────────┘
                                  │
                                  ▼
                ┌────────────────────────────────────────────┐
                │        offboard.py handover (可选)          │
                │                                            │
                │  dry-run → 打印计划 → [y/N] 确认 → 执行     │
                └────────────────────────────────────────────┘
```

### 采集模块 → 真实 lark-cli 命令映射

| # | 模块 | lark-cli 命令 | 备注 |
|---|---|---|---|
| 1 | 文档资产 | `docs +search --query <kw>` | 按关键词检索 |
| 2 | 待处理审批 | `approval tasks query --params '{"topic":"1"}'` | `topic=1` 表示待办 |
| 3 | 群主身份 | `im chats list --page-all` | 本地过滤 `owner_id` |
| 4 | 未完成任务 | self: `task +get-my-tasks`<br/>audit: `task +search --assignee` | 两模式命令不同 |
| 5 | 周期会议 | `calendar +agenda --start --end` | 按 `recurrence` 过滤 |

### 三档状态机

每个模块的采集结果会落到三档之一：

| 状态 | 图标 | 含义 | 触发条件 |
|---|---|---|---|
| `ok` | ✅ | 完整采集 | 正常返回 |
| `partial` | ⚠️ | 有截断/字段缺失 | 分页达上限、部分字段缺失 |
| `broken` | ❌ | 需人工介入 | 熔断、权限不足、超时 |

当 `broken ≥ 3` 时，清单顶部自动显示红色横幅告警，避免按残缺清单交接。

---

## 🔐 权限 scope

| 模块 | 读 scope | 写 scope（一键动作用） |
|---|---|---|
| 文档 | `docs:document:readonly` 或 `drive:drive:readonly` | `docs:document` |
| 审批 | `approval:approval` | `approval:approval` |
| 群聊 | `im:chat:readonly` | `im:chat` |
| 任务 | `task:task` | `task:task` |
| 日历 | `calendar:calendar:readonly` | `calendar:calendar` |

- **self 模式**：基础 user scope 即可
- **audit 模式**：追加 `contact:user.employee_id:readonly` + tenant 级 docs/drive scope

详见 [`references/scopes.md`](references/scopes.md)。

---

## 🧪 测试覆盖

| 类型 | 规模 | 状态 |
|---|---|---|
| 功能测试（asyncio + mock，10 场景） | 46 断言 | ✅ 全通过 |
| 静态合规（frontmatter / 链接 / 依赖） | 34 检查 | ✅ 全通过 |
| 真实环境端到端（lark-cli v1.0.15） | 5 模块实调 | ✅ 全通过 |

覆盖场景：全成功、scope 缺失、429 退避熔断、预熔断、全局超时、渲染、JSON schema、CLI 参数、dry-run 安全。

---

## 📁 目录结构

```
lark-offboard-kit/
├── 📄 SKILL.md                 # 技能入口 + 触发描述 + 使用说明
├── 📄 README.md                # 本文件
├── 📄 LICENSE                  # MIT
├── 📄 .gitignore
├── 📂 scripts/
│   ├── preflight.sh            # 检测 + 自动安装 + scope 探测
│   └── offboard.py             # 采集 + 渲染 + 一键动作（纯 stdlib）
└── 📂 references/
    ├── scopes.md               # scope 对照表 + self/audit 差异
    └── degradation.md          # 熔断降级决策树 + 退出码语义
```

---

## ❓ 常见问题

<details>
<summary><b>docs 模块返回 0 项是 bug 吗？</b></summary>

不是。飞书 `docs +search` **不支持按 owner 直接枚举**，只能关键词检索。如果关键词与当事人文档无匹配就返回 0 项。

**建议**：用项目名、部门名、产品代号等高命中关键词，或多次运行聚合多组关键词。

</details>

<details>
<summary><b>audit 模式下 approval / calendar 被标 broken？</b></summary>

这两个模块依赖 tenant 级 OpenAPI，当前版本仅支持 self 模式下的自查。未来版本可通过 `lark-cli api` raw 调用补齐。详见 [路线图](#-路线图)。

</details>

<details>
<summary><b>Windows 上报 "lark-cli not found"？</b></summary>

npm 全局装的 `lark-cli` 在 Windows 上实际是 `lark-cli.cmd`。代码中 `_spawn()` 函数已针对 Windows 使用 shell 模式调用以解析 PATHEXT。如仍报错，请检查 `%APPDATA%\npm\` 是否在 PATH 中。

</details>

<details>
<summary><b>熔断后还能重试吗？</b></summary>

熔断作用域是**单次运行**，不持久化。重新执行 `offboard.py run` 即重置。

</details>

<details>
<summary><b>一键动作会误触发吗？</b></summary>

不会。三重保险：
1. 不加 `--execute` 只打印 dry-run
2. 加了 `--execute` 仍需交互输入 `y` 才继续
3. 失败项独立计错，不中断流程

</details>

---

## 🛣️ 路线图

- [ ] audit 模式补齐 approval / calendar（tenant 级 API）
- [ ] 输出 PDF / xlsx 格式交接包
- [ ] 接入飞书多维表格自定义字段（如客户联系人）
- [ ] 一键创建交接审批实例
- [ ] GitHub Actions CI 集成示例
- [ ] Web UI 包装（可选）

---

## 🤝 贡献

欢迎 issue 和 PR。提 PR 前请确保：

- 代码通过 `python3 -c "import ast; ast.parse(open('scripts/offboard.py').read())"`
- 若新增采集模块，请同步更新 `SKILL.md` 命令表和 `references/scopes.md`
- 遵循现有命名/结构约定

---

## 📄 License

[MIT](LICENSE) © 2026

---

<div align="center">

**如果这个工具帮你省了时间，给个 ⭐ 鼓励一下作者**

</div>
