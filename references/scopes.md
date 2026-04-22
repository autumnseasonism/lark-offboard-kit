# scope 对照表

每个模块需要的飞书开放平台 scope。`lark-cli auth login --recommend` 会按当前 skill 推荐集合索要授权；也可以用 `lark-cli auth login --scope <scope>` 精确控制。

## 读取（采集阶段）

| 模块 | 必需 scope | 说明 |
|---|---|---|
| 文档资产 | `docs:document:readonly` 或 `drive:drive:readonly` | 至少一个。`drive` 覆盖范围更广（含非 docx 类型） |
| 待处理审批 | `approval:approval` | 读写合一的 scope |
| 群主身份 | `im:chat:readonly` | 仅列群；需读取 `owner_id` 字段 |
| 未完成任务 | `task:task` | 读写合一 |
| 周期会议（日历） | `calendar:calendar:readonly` | 读日程；无 `--user` 他人读取时需 tenant scope |

## 写入（一键动作阶段）

| 动作 | 必需 scope |
|---|---|
| 转群主 `im +chat-update --owner` | `im:chat`（非 readonly） |
| 转任务 `task +update --assignee` | `task:task` |
| 发起交接审批 `approval +create` | `approval:approval` |
| 创建交接文档 `docs +create` | `docs:document` |

## self vs audit 模式的 scope 差异

| scope | self 模式够用 | audit 模式要求 |
|---|---|---|
| `contact:user.base:readonly` | ✓ 查自己 | ✗ 查他人需 `contact:user.employee_id:readonly` |
| `docs:*` user 级 | ✓ | ✗ 要 tenant 级才能按 owner 筛他人文档 |
| `im:chat:readonly` user 级 | ✓ 自己的群 | ⚠️ tenant 级可枚举全部群 |
| `task:task` | ✓ 自己任务 | ✗ 他人任务需管理员 scope |

**运行时降级**：`preflight.sh` 探测到 scope 不足时写入 `.offboard-cache/scopes.json`；`offboard.py` 读取后把对应模块预标熔断，避免无谓调用，并在报告中显式提示。

## 最小授权建议

- **员工自查场景**：5 个 `*:readonly` + 3 个写 scope（`im:chat` / `task:task` / `approval:approval`）
- **HR 审计场景**：追加 `contact:user.employee_id:readonly` + 协商 tenant 级 `docs`/`drive` scope
