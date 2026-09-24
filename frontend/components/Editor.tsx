"use client";
import { uiText, uiFormat } from "@/lib/i18n";

import { useEffect, useRef, useState } from "react";
import {
  X,
  Trash2,
  ArrowRight,
  Clock3,
  Repeat2,
  Layers3,
  CalendarDays,
  CheckCircle2,
} from "lucide-react";
import { api, send, statusLabel, zonedInput, zonedISO } from "@/lib/api";
import type { Bootstrap, EditorState, Task } from "@/lib/types";

const names = {
  task: "任务",
  goal: "目标",
  project: "项目",
  milestone: "里程碑",
  routine: "重复任务",
  event: "日历事件",
};
const resources = {
  task: "tasks",
  goal: "goals",
  project: "projects",
  milestone: "milestones",
  routine: "routines",
  event: "events",
};

export default function Editor({
  editor,
  data,
  close,
  saved,
}: {
  editor: EditorState;
  data: Bootstrap;
  close: () => void;
  saved: (message: string) => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const { kind, item } = editor;
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const base: Record<string, unknown> = Object.assign(
      {
        name: "",
        title: "",
        description: "",
        start_date: data.today,
        date: data.today,
        priority: 2,
        status: "active",
        color: "#acbcf7",
        estimated_duration: 30,
        frequency: "daily",
        interval: 1,
        interval_unit: "days",
        weekdays: [0, 1, 2, 3, 4],
        active: true,
        offset_days: 1,
        reminder: "",
        start: `${data.today}T09:00`,
        end: `${data.today}T10:00`,
        all_day: false,
      },
      editor.defaults || {},
      item || {},
    );
    if (kind === "task" && base.deadline)
      base.deadline = zonedInput(String(base.deadline), data.settings.timezone);
    return base;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<
    { id: string; action: string; created_at: string }[] | null
  >(null);
  const set = (key: string, value: unknown) =>
    setValues((v) => ({ ...v, [key]: value }));
  const str = (key: string) => (values[key] == null ? "" : String(values[key]));
  const num = (key: string) => Number(values[key]);
  const nullable = (key: string) => str(key) || null;
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  const field = (
    key: string,
    label: string,
    type = "text",
    required = false,
    extra: Record<string, string | number> = {},
  ) => (
    <label className="field" key={key}>
      <span>
        {label}
        {required && <b> *</b>}
      </span>
      <input
        type={type}
        value={str(key)}
        onInput={(e) => set(key, e.currentTarget.value)}
        onChange={(e) => set(key, e.target.value)}
        required={required}
        {...extra}
      />
    </label>
  );
  const select = (
    key: string,
    label: string,
    options: [string, string][],
    required = false,
  ) => (
    <label className="field" key={key}>
      <span>
        {label}
        {required && <b> *</b>}
      </span>
      <select
        value={str(key)}
        required={required}
        onChange={(e) => {
          set(key, e.target.value);
          if (key === "project_id") set("milestone_id", "");
        }}
      >
        {options.map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
  const projectSelect = () =>
    select(
      "project_id",
      uiText("所属项目"),
      [
        ["", uiText("独立任务 / 暂不归属")],
        ...data.projects.map((p) => [p.id, p.name] as [string, string]),
      ],
      kind === "milestone",
    );
  const milestoneSelect = () =>
    select("milestone_id", uiText("所属里程碑"), [
      ["", uiText("暂不设置")],
      ...data.milestones
        .filter((m) => m.project_id === str("project_id"))
        .map((m) => [m.id, m.name] as [string, string]),
    ]);
  const prioritySelect = () =>
    select("priority", uiText("优先级"), [
      ["1", uiText("高 · 优先处理")],
      ["2", uiText("中 · 正常安排")],
      ["3", uiText("低 · 灵活安排")],
    ]);
  const reminderSelect = () =>
    select("reminder", uiText("任务提醒"), [
      ["", uiText("不提醒")],
      ["0", uiText("准时提醒")],
      ["10", uiText("提前 10 分钟")],
      ["30", uiText("提前 30 分钟")],
      ["60", uiText("提前 1 小时")],
      ["1440", uiText("提前 1 天")],
    ]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      let payload: Record<string, unknown>;
      const organization = {
        name: str("name"),
        description: str("description"),
        start_date: nullable("start_date"),
        status: str("status"),
      };
      if (kind === "goal")
        payload = {
          ...organization,
          target_date: nullable("target_date"),
          priority: num("priority"),
          color: str("color"),
        };
      else if (kind === "project")
        payload = {
          ...organization,
          goal_id: nullable("goal_id"),
          end_date: nullable("end_date"),
        };
      else if (kind === "milestone")
        payload = {
          ...organization,
          project_id: str("project_id"),
          deadline: nullable("deadline"),
        };
      else if (kind === "task") {
          const startTime = nullable("start_time");
          const endTime = nullable("end_time");
          if (Boolean(startTime) !== Boolean(endTime))
            throw new Error(uiText("开始时间和结束时间需要同时填写"));
          let estimatedDuration = 0;
          if (startTime && endTime) {
            const [startHour, startMinute] = startTime.split(":").map(Number);
            const [endHour, endMinute] = endTime.split(":").map(Number);
            estimatedDuration = endHour * 60 + endMinute - startHour * 60 - startMinute;
            if (estimatedDuration <= 0)
              throw new Error(uiText("结束时间必须晚于开始时间"));
          }
          payload = {
            title: str("title"),
            description: str("description"),
            project_id: nullable("project_id"),
            milestone_id: nullable("milestone_id"),
            date: nullable("date"),
            start_time: startTime,
            end_time: endTime,
            deadline: zonedISO(str("deadline"), data.settings.timezone),
            estimated_duration: estimatedDuration,
            priority: num("priority"),
            reminder: str("reminder") === "" ? null : num("reminder"),
            depends_on_task_id: nullable("depends_on_task_id"),
            version: item ? num("version") : null,
          };
      } else if (kind === "routine")
        payload = {
          name: str("name"),
          description: str("description"),
          project_id: nullable("project_id"),
          milestone_id: nullable("milestone_id"),
          frequency: str("frequency"),
          interval: num("interval"),
          interval_unit: str("interval_unit"),
          weekdays: values.weekdays,
          start_date: str("start_date"),
          end_date: nullable("end_date"),
          preferred_time: nullable("preferred_time"),
          estimated_duration: num("estimated_duration"),
          priority: num("priority"),
          reminder: str("reminder") === "" ? null : num("reminder"),
          active: Boolean(values.active),
          depends_on_routine_id: nullable("depends_on_routine_id"),
          offset_days: nullable("depends_on_routine_id")
            ? num("offset_days")
            : 0,
          version: item ? num("version") : null,
        };
      else
        payload = {
          title: str("title"),
          description: str("description"),
          start: str("start"),
          end: str("end"),
          all_day: Boolean(values.all_day),
          color: str("color"),
        };
      await send(
        `/${resources[kind]}${item ? `/${item.id}` : ""}`,
        payload,
        item ? "PUT" : "POST",
      );
      await saved(uiFormat("{0}已{1}", uiText(names[kind]), item ? uiText("更新") : uiText("创建")));
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : uiText("保存失败，请重试"));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (
      !item ||
      !window.confirm(
        uiFormat("删除“{0}”？有关联内容的目标、项目和里程碑需要先移除关联。任务删除后会保留历史记录。", str("title") || str("name")),
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await api(
        `/${resources[kind]}/${item.id}${kind === "task" || kind === "routine" ? `?version=${num("version")}` : ""}`,
        { method: "DELETE" },
      );
      await saved(uiFormat("{0}已删除", uiText(names[kind])));
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function showHistory() {
    try {
      setHistory(await api(`/tasks/${item?.id}/history`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function taskOperation() {
    if (!item || kind !== "task") return;
    setBusy(true);
    setError("");
    try {
      const action = ["completed", "cancelled"].includes(str("status"))
        ? "reopen"
        : "complete";
      await send(`/tasks/${item.id}/actions`, {
        action,
        version: num("version"),
      });
      await saved(action === "complete" ? uiText("完成记录已保存") : uiText("任务已重新打开"));
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      className="editor-dialog"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) close();
      }}
      onClick={(e) => {
        if (e.target === dialog.current && !busy) close();
      }}
    >
      <div className="dialog-head">
        <div className="dialog-icon">
          {kind === "routine" ? (
            <Repeat2 size={21} />
          ) : kind === "event" ? (
            <CalendarDays size={21} />
          ) : kind === "task" ? (
            <CheckCircle2 size={21} />
          ) : (
            <Layers3 size={21} />
          )}
        </div>
        <div>
          <h2>
            {item ? uiText("编辑") : uiText("新建")}
            {uiText(names[kind])}
          </h2>
        </div>
        <button
          className="icon-button close-dialog"
          aria-label={uiText("关闭")}
          onClick={close}
          disabled={busy}
        >
          <X size={20} />
        </button>
      </div>
      <form onSubmit={submit}>
        <div className="dialog-body">
          {kind === "task" || kind === "event"
            ? field("title", uiText("名称"), "text", true, {
                maxLength: 200,
                placeholder: uiText("给这件事起个清晰的名字"),
              })
            : field("name", uiText("名称"), "text", true, {
                maxLength: 200,
                placeholder: uiText("你想推进的事情"),
              })}
          <label className="field">
            <span>{uiText("描述 / 备注")}</span>
            <textarea
              rows={3}
              value={str("description")}
              onChange={(e) => set("description", e.target.value)}
              maxLength={10000}
              placeholder={uiText("可选：记录背景、完成标准或需要的材料")}
            />
          </label>
          {(kind === "goal" || kind === "project" || kind === "milestone") && (
            <>
              {kind === "project" &&
                select("goal_id", uiText("所属目标"), [
                  ["", uiText("独立项目")],
                  ...data.goals.map((g) => [g.id, g.name] as [string, string]),
                ])}
              {kind === "milestone" && projectSelect()}
              <div className="form-grid">
                {field("start_date", uiText("开始日期"), "date")}
                {field(
                  kind === "goal"
                    ? "target_date"
                    : kind === "project"
                      ? "end_date"
                      : "deadline",
                  uiText("目标日期"),
                  "date",
                )}
              </div>
              <div className="form-grid">
                {select("status", uiText("状态"), [
                  ["active", uiText("进行中")],
                  ["paused", uiText("已暂停")],
                  ["completed", uiText("已完成")],
                  ["archived", uiText("已归档")],
                ])}
                {kind === "goal" && prioritySelect()}
              </div>
              {kind === "goal" && field("color", uiText("目标颜色"), "color")}
            </>
          )}
          {kind === "task" && (
            <>
              <div className="form-grid">
                {projectSelect()}
                {milestoneSelect()}
              </div>
              <div className="form-divider">
                <Clock3 size={15} /> {uiText("时间安排")}{" "}
                <span>{data.settings.timezone}</span>
              </div>
              {field("date", uiText("计划日期"), "date")}
              <div className="form-grid">
                {field("start_time", uiText("开始时间"), "time")}
                {field("end_time", uiText("结束时间"), "time")}
              </div>
              <div className="form-grid">
                {field("deadline", uiText("截止时间"), "datetime-local")}
                {prioritySelect()}
              </div>
              <div className="form-grid">
                {reminderSelect()}
                {select("depends_on_task_id", uiText("依赖任务（先完成）"), [
                  ["", uiText("没有依赖")],
                  ...data.tasks
                    .filter(
                      (t) => t.id !== item?.id && t.status !== "cancelled",
                    )
                    .map(
                      (t) =>
                        [t.id, `${t.title}${t.date ? ` · ${t.date}` : ""}`] as [
                          string,
                          string,
                        ],
                    ),
                ])}
              </div>
              <p className="form-hint">
                {uiText("预计用时会根据开始时间和结束时间自动计算。未设置时间时，按每日默认开始时间提醒。依赖未完成的任务会显示等待状态。")}
              </p>
              {item && (
                <div className="record-meta">
                  <span>{uiText("状态：")}{statusLabel(str("status"))}</span>
                  <span>
                    {uiText("来源：")}
                    {str("source") === "routine" ? uiText("重复任务") : uiText("手动创建")}
                  </span>
                  <button
                    type="button"
                    className="text-button"
                    onClick={showHistory}
                  >
                    {uiText("查看变更记录")}
                  </button>
                </div>
              )}
              {history && (
                <div className="history-list">
                  {history.length ? (
                    history.map((h) => (
                      <div key={h.id}>
                        <span>
                          {(
                            {
                              created: uiText("创建"),
                              updated: uiText("修改"),
                              completed: uiText("完成"),
                              reopened: uiText("重新打开"),
                              rescheduled: uiText("改期"),
                              cancelled: uiText("取消"),
                              deleted: uiText("删除"),
                              complete: uiText("完成"),
                              reopen: uiText("重新打开"),
                              reschedule: uiText("改期"),
                              cancel: uiText("取消"),
                              keep_overdue: uiText("保留逾期"),
                            } as Record<string, string>
                          )[h.action] || h.action}
                        </span>
                        <time>
                          {new Date(h.created_at).toLocaleString("zh-CN", {
                            timeZone: data.settings.timezone,
                          })}
                        </time>
                      </div>
                    ))
                  ) : (
                    <p>{uiText("尚无变更记录")}</p>
                  )}
                </div>
              )}
            </>
          )}
          {kind === "routine" && (
            <>
              <div className="form-grid">
                {projectSelect()}
                {milestoneSelect()}
              </div>
              <div className="form-divider">
                <Repeat2 size={15} /> {uiText("重复规则")}
              </div>
              {select("frequency", uiText("重复频率"), [
                ["daily", uiText("每天 · Daily")],
                ["every_n_days", uiText("每 N 天 · Every N Days")],
                ["weekly", uiText("每周 · Weekly")],
                ["weekdays", uiText("指定星期 · Specific Weekdays")],
                ["custom", uiText("自定义间隔 · Custom Interval")],
              ])}
              {str("frequency") !== "daily" && (
                <div className="form-grid">
                  {field(
                    "interval",
                    ["weekly", "weekdays"].includes(str("frequency"))
                      ? uiText("每隔几周")
                      : uiText("间隔"),
                    "number",
                    true,
                    { min: 1, max: 365 },
                  )}
                  {str("frequency") === "custom" &&
                    select("interval_unit", uiText("间隔单位"), [
                      ["days", uiText("天")],
                      ["weeks", uiText("周")],
                    ])}
                </div>
              )}
              {str("frequency") === "weekdays" && (
                <fieldset className="weekday-field">
                  <legend>{uiText("重复星期")}</legend>
                  <div>
                    {[uiText("一"), uiText("二"), uiText("三"), uiText("四"), uiText("五"), uiText("六"), uiText("日")].map(
                      (day, index) => (
                        <label
                          key={day}
                          className={
                            (values.weekdays as number[]).includes(index)
                              ? "selected"
                              : ""
                          }
                        >
                          <input
                            type="checkbox"
                            checked={(values.weekdays as number[]).includes(
                              index,
                            )}
                            onChange={(e) =>
                              set(
                                "weekdays",
                                e.target.checked
                                  ? [...(values.weekdays as number[]), index]
                                  : (values.weekdays as number[]).filter(
                                      (i) => i !== index,
                                    ),
                              )
                            }
                          />
                          {day}
                        </label>
                      ),
                    )}
                  </div>
                </fieldset>
              )}
              {str("frequency") === "weekly" && (
                <p className="form-hint">
                  {uiText("从开始日期起，每隔")} {num("interval")} {uiText("周的同一天生成任务。")}
                </p>
              )}
              <p className="form-hint">
                {uiText("名称可使用")} {"{n}"} {uiText("自动编号、")}{"{date}"}{" "}
                {uiText("插入原始日期；单次改期不会改变编号。")}
              </p>
              <div className="form-grid">
                {field("start_date", uiText("开始日期"), "date", true)}
                {field("end_date", uiText("结束日期（可不填）"), "date")}
              </div>
              <div className="form-grid">
                {field("preferred_time", uiText("默认开始时间"), "time")}
                {field(
                  "estimated_duration",
                  uiText("预计用时（分钟）"),
                  "number",
                  true,
                  { min: 1, max: 1440 },
                )}
              </div>
              <div className="form-grid">
                {prioritySelect()}
                {reminderSelect()}
              </div>
              <div className="form-divider">
                <ArrowRight size={15} /> {uiText("简单依赖")}
              </div>
              {select("depends_on_routine_id", uiText("依赖的重复任务"), [
                ["", uiText("没有依赖")],
                ...data.routines
                  .filter((r) => r.id !== item?.id)
                  .map((r) => [r.id, r.name] as [string, string]),
              ])}
              {str("depends_on_routine_id") && (
                <>
                  {field("offset_days", uiText("依赖前几天的任务"), "number", true, {
                    min: 0,
                    max: 365,
                  })}
                  <p className="form-hint">
                    {uiText("填 1 表示：今天生成的任务依赖所选重复规则在昨天生成的任务。请让本规则开始日期至少晚于依赖规则相应天数。")}
                  </p>
                </>
              )}
              <label className="toggle-line">
                <input
                  type="checkbox"
                  checked={Boolean(values.active)}
                  onChange={(e) => set("active", e.target.checked)}
                />
                <span>{uiText("启用规则，自动生成任务")}</span>
              </label>
              <p className="form-hint">
                {uiText("修改规则会更新尚未修改的未来任务；完成记录和手动调整会保留。")}
              </p>
            </>
          )}
          {kind === "event" && (
            <>
              <label className="toggle-line">
                <input
                  type="checkbox"
                  checked={Boolean(values.all_day)}
                  onChange={(e) => {
                    const allDay = e.target.checked;
                    setValues((v) => ({
                      ...v,
                      all_day: allDay,
                      start:
                        String(v.start).slice(0, 10) + (allDay ? "" : "T09:00"),
                      end:
                        String(v.end).slice(0, 10) + (allDay ? "" : "T10:00"),
                    }));
                  }}
                />
                {uiText("全天事件")}
              </label>
              <div className="form-grid">
                {field(
                  "start",
                  uiText("开始"),
                  values.all_day ? "date" : "datetime-local",
                  true,
                )}
                {field(
                  "end",
                  values.all_day ? uiText("结束（不含当日）") : uiText("结束"),
                  values.all_day ? "date" : "datetime-local",
                  true,
                )}
              </div>
              {field("color", uiText("事件颜色"), "color")}
              <p className="form-hint">
                {uiText("独立日历事件用于安排时间，不计入任务完成率。时间按")}{" "}
                {data.settings.timezone} {uiText("记录。")}
              </p>
            </>
          )}
          {error && (
            <div role="alert" className="form-error">
              {error}
            </div>
          )}
        </div>
        <div className="dialog-foot">
          {item && (
            <button
              type="button"
              className="button danger subtle"
              disabled={busy}
              onClick={remove}
            >
              <Trash2 size={16} />
              {uiText("删除")}
            </button>
          )}
          {item && kind === "task" && (
            <button
              type="button"
              className="button secondary"
              disabled={
                busy ||
                (!["completed", "cancelled"].includes(str("status")) &&
                  (item as Task).blocked)
              }
              onClick={taskOperation}
            >
              <CheckCircle2 size={15} />
              {["completed", "cancelled"].includes(str("status"))
                ? uiText("重新打开")
                : uiText("标记完成")}
            </button>
          )}
          <div className="dialog-foot-spacer" />
          <button
            type="button"
            className="button secondary"
            onClick={close}
            disabled={busy}
          >
            {uiText("取消")}
          </button>
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? uiText("正在保存…") : item ? uiText("保存修改") : uiFormat("创建{0}", uiText(names[kind]))}
            <ArrowRight size={16} />
          </button>
        </div>
      </form>
    </dialog>
  );
}
