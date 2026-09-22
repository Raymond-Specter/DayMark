import type { Task } from "./types";
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : Array.isArray(body.detail)
            ? body.detail
                .map(
                  (e: { loc: string[]; msg: string }) =>
                    `${e.loc.slice(1).join(" / ")}：${e.msg}`,
                )
                .join("；")
            : message;
    } catch {
      /* Keep HTTP error. */
    }
    throw new Error(message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export const send = <T>(path: string, body: unknown, method = "POST") =>
  api<T>(path, { method, body: JSON.stringify(body) });
export function taskPayload(task: Task) {
  const {
    title,
    description,
    project_id,
    milestone_id,
    date,
    start_time,
    end_time,
    deadline,
    estimated_duration,
    priority,
    depends_on_task_id,
    reminder,
    track_learning,
    version,
  } = task;
  return {
    title,
    description,
    project_id,
    milestone_id,
    date,
    start_time,
    end_time,
    deadline,
    estimated_duration,
    priority,
    depends_on_task_id,
    reminder,
    track_learning,
    version,
  };
}
export const priorityLabel = (value: number) =>
  ["", "高优先级", "中优先级", "低优先级"][value] || "中优先级";
export const statusLabel = (value: string) =>
  ({
    pending: "待完成",
    completed: "已完成",
    overdue: "已逾期",
    rescheduled: "已改期",
    cancelled: "已取消",
    active: "进行中",
    paused: "已暂停",
    archived: "已归档",
  })[value] || value;
export function localDate(value = new Date()) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}
export function dateLabel(value: string | null, compact = false) {
  if (!value) return "未安排日期";
  return new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString(
    "zh-CN",
    compact
      ? { month: "short", day: "numeric" }
      : { month: "long", day: "numeric", weekday: "long" },
  );
}
export function hours(minutes: number) {
  return Number((minutes / 60).toFixed(1));
}
export function deadlineLabel(value: string, timezone: string) {
  return new Date(value).toLocaleString("zh-CN", {
    timeZone: timezone,
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
export function zonedInput(value: string, timezone: string) {
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value));
  return parts.replace(" ", "T");
}
export function zonedISO(value: string, timezone: string) {
  if (!value) return null;
  const intended = Date.parse(`${value}:00Z`);
  let candidate = intended;
  for (let n = 0; n < 3; n++) {
    const actualWall = Date.parse(
      `${zonedInput(new Date(candidate).toISOString(), timezone)}:00Z`,
    );
    candidate += intended - actualWall;
  }
  if (zonedInput(new Date(candidate).toISOString(), timezone) !== value)
    throw new Error("该时间在所选时区不存在，请选择其他时间");
  return new Date(candidate).toISOString();
}
