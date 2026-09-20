# API 设计

后端默认 `http://127.0.0.1:8000`；浏览器通过前端同源 `/api` 访问。实时、准确的字段定义以运行时 `/docs` 和 `/openapi.json` 为准。除 `/health` 外，下表路径均以 `/api` 开头。

## 基本约定

- JSON 请求/响应，UUID 资源 ID。创建/完整修改使用后端 Schema 验证，未知字段拒绝。
- 日期 `YYYY-MM-DD`、时间 `HH:MM`、UTC 瞬间为带偏移的 ISO 8601；Task deadline 请求必须带时区。
- 优先级 1 高、2 中、3 低；weekday 0 周一至 6 周日；时长/提醒提前量为分钟。
- Task / Routine 修改带当前 `version`；版本冲突为 `409`，应刷新资源后再操作。
- 日期区间查询按对应端点定义；日历 `end` 为排除上界，与 FullCalendar 保持一致。
- 业务错误带 `detail`；资源不存在为 `404`，输入错误为 `422`，关联/状态/版本冲突返回相应错误。

## 页面读模型

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /health | 应用健康：status=ok、service=personal-planning、schema 版本；此路径不加 /api |
| GET | /bootstrap | 页面初始所需组织结构、规则和设置等数据 |
| GET | /today | 今日任务、完成/剩余、昨日遗留、临近截止等聚合数据 |
| GET | /progress | Goal / Project / Milestone 进度与当前阶段 |
| GET | /statistics?start=…&end=… | 指定日期范围的完成情况与时间统计 |
| GET | /calendar?start=…&end=… | 指定日期范围内的日历事件，end 不包含 |

## 组织管理

对 `goals`、`projects`、`milestones` 分别提供：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /{resource} | 获取列表 |
| POST | /{resource} | 新建 |
| PUT | /{resource}/{id} | 修改 |
| DELETE | /{resource}/{id} | 删除；存在子项或被引用时阻止 |

Goal 输入包含 name、description、start_date、target_date、status、priority、color。Project 输入增加 goal_id、end_date。Milestone 需要 project_id，可设 deadline。日期为空可暂不设时间边界。

## Task

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /tasks | 任务列表，筛选参数见 OpenAPI |
| GET | /tasks/{id} | 读取单个任务及派生依赖状态 |
| POST | /tasks | 创建手动任务 |
| PUT | /tasks/{id} | 更新任务；带 version |
| DELETE | /tasks/{id}?version=… | 软删除；保留重复发生唯一键与审计 |
| POST | /tasks/{id}/actions | complete / reopen / reschedule / cancel / keep_overdue |
| GET | /tasks/{id}/history | 操作历史 |

示例：

```json
{
  "title": "我自己创建的任务",
  "description": "",
  "project_id": null,
  "milestone_id": null,
  "date": "2026-09-20",
  "start_time": "09:00",
  "end_time": "10:00",
  "estimated_duration": 60,
  "priority": 2,
  "reminder": 10,
  "depends_on_task_id": null
}
```

完成动作请求：`{"action":"complete","version":1}`。延期请求：`{"action":"reschedule","date":"2026-09-21","version":1}`；可同时传新的 start_time / end_time。业务状态不能靠任意字段直接覆盖。

## Routine 与 Scheduler

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET / POST | /routines | 列表 / 创建 |
| PUT | /routines/{id} | 更新规则；带 version |
| DELETE | /routines/{id} | 删除规则；具体引用限制见响应，不删除已有完成记录 |
| POST | /scheduler/sync | 按窗口生成实例；请求可含 start / end |

Routine 输入为 name、description、project_id、milestone_id、frequency、interval、interval_unit、weekdays、start_date、end_date、preferred_time、estimated_duration、priority、reminder、active、depends_on_routine_id、offset_days。`frequency` 支持 daily / every_n_days / weekly / weekdays / custom；custom 间隔单位为 days / weeks。

默认同步从连续生成水位 `materialized_through` 之后补齐至今天之后 30 天；首次从规则起始日期开始。显式 start / end 均包含边界，窗口最多 367 天，可位于任意远期；只有 end 没有 start 时，最多到今天之后 366 天。日历可以查询任意远期日期，单次查询为 1–366 天，end 排除上界。远期孤立窗口不推进连续生成水位，防止跳过中间任务；编辑规则不重算旧日期。

暂停后恢复时，跳过暂停期间尚未生成的日期；已因暂停取消的过去实例保持取消。未来且未经人工处理的匹配实例可恢复。`weekly` 从 start_date 对应的星期开始，每 interval 周重复；`weekdays` 按周一对齐的周周期匹配选中星期。名称可使用 `{n}`（规则实例序号）和 `{date}`（原始日期）占位符。

## 日历、回顾、提醒与设置

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | /events | 创建独立日历事件 |
| PUT / DELETE | /events/{id} | 修改 / 删除独立事件 |
| GET / PUT | /reviews/{date} | 读取 / 保存当日回顾与任务快照 |
| GET / PUT | /settings | 读取 / 设置 IANA 时区和默认日开始时间 |
| POST | /reminders/dispatch | 派发已到期提醒，幂等生成站内通知 |
| GET | /notifications | 通知列表 |
| POST | /notifications/{id}/read | 标记通知已读 |
| GET | /export | JSON 数据导出 |
| GET | /integrations | 返回预留集成能力与未连接状态 |

Event 输入：title、start、end、all_day、description、color。非全天事件用不带时区的本地日期时间；全天用日期，end 排除上界。

Task 日程与独立事件都采用设置时区的本地时间。单次 Task 不跨午夜，未填写结束时间时，自动推算的结束时间也必须在当天内。依赖更新同时校验 Routine 图与实际 Task 图；闭环返回输入错误。提醒派发对工作 ID 幂等，同一 Task 的同一 due_at 已派发后，仅编辑标题不重复提醒。

Review 输入：actual_minutes、energy_level、notes、project_minutes（项目 ID → 分钟）。实际时间为 0–1440、精力为 1–5；项目分钟合计不能超过实际分钟。完成/未完成任务列表由服务在保存时生成快照。

Task 列表 start / end 均包含边界，可按 status / project_id 筛选。统计 start / end 也包含边界；今日/本周完成数按实际 completed_at 所属本地日期计数，范围完成率按计划 date 所在范围内的未取消任务计算。Today 的完成数是「今天计划的任务已完成多少」，与「今天实际勾选完成多少」语义不同。

## 未来接口边界

Google Calendar、OpenAI 和 AI 规划在能力列表中保持未连接；不提供伪装成成功的占位调用。外部推送和日历同步未来通过独立 provider 实现，不改变基础 Task 管理契约。
