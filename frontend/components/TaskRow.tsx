import {
  Check,
  Clock3,
  Flag,
  Link2,
  MoreHorizontal,
  Repeat2,
  Pencil,
  CalendarDays,
  X,
  RotateCcw,
} from "lucide-react";
import { dateLabel, priorityLabel, statusLabel } from "@/lib/api";
import type { Bootstrap, Task } from "@/lib/types";
export type TaskAction =
  "complete" | "reopen" | "reschedule" | "cancel" | "keep_overdue";
export default function TaskRow({
  task,
  data,
  action,
  edit,
  reschedule,
  busy,
  showDate = false,
  overdueActions = false,
}: {
  task: Task;
  data: Bootstrap;
  action: (task: Task, action: TaskAction, date?: string) => void;
  edit: (task: Task) => void;
  reschedule: (task: Task) => void;
  busy?: boolean;
  showDate?: boolean;
  overdueActions?: boolean;
}) {
  const project = data.projects.find((p) => p.id === task.project_id);
  const color =
    data.goals.find((g) => g.id === project?.goal_id)?.color || "#315e70";
  const completed = task.status === "completed";
  const cancelled = task.status === "cancelled";
  return (
    <div
      className={`task-row ${completed ? "is-complete" : ""} ${cancelled ? "is-cancelled" : ""}`}
    >
      <button
        className={`task-check ${completed ? "checked" : ""}`}
        aria-label={completed ? `重新打开 ${task.title}` : `完成 ${task.title}`}
        disabled={busy || (!completed && task.blocked) || cancelled}
        title={task.blocked ? task.blocked_reason || "依赖任务尚未完成" : ""}
        onClick={() => action(task, completed ? "reopen" : "complete")}
      >
        {completed && <Check size={13} strokeWidth={3} />}
      </button>
      <div className="task-row-content">
        <button className="task-title" onClick={() => edit(task)}>
          {task.title}
        </button>
        <div className="task-meta">
          {project && (
            <span className="project-label">
              <i style={{ backgroundColor: color }} />
              {project.name}
            </span>
          )}
          {showDate && (
            <span>
              <CalendarDays size={12} />
              {dateLabel(task.date, true)}
            </span>
          )}
          <span>
            <Clock3 size={12} />
            {task.start_time
              ? `${task.start_time}${task.end_time ? `–${task.end_time}` : ""}`
              : "时间待定"}
          </span>
          <span>{task.estimated_duration} 分钟</span>
          {task.routine_id && (
            <span>
              <Repeat2 size={12} />
              重复
            </span>
          )}
          {task.status !== "pending" && (
            <span className={`task-state ${task.status}`}>
              {statusLabel(task.status)}
            </span>
          )}
        </div>
        {task.blocked && (
          <div className="dependency-hint">
            <Link2 size={11} />
            {task.blocked_reason ||
              `等待：${task.dependency_title || "前置任务"}`}
          </div>
        )}
        {overdueActions && (
          <div className="unfinished-actions">
            <button onClick={() => action(task, "reschedule", data.today)}>
              移至今天
            </button>
            <button onClick={() => reschedule(task)}>选择日期</button>
            <button onClick={() => action(task, "cancel")}>标记取消</button>
            <button onClick={() => action(task, "keep_overdue")}>
              保留逾期
            </button>
          </div>
        )}
      </div>
      <span
        className={`priority-badge p${task.priority}`}
        title={priorityLabel(task.priority)}
      >
        <Flag size={11} fill="currentColor" />
        {["", "高", "中", "低"][task.priority]}
      </span>
      <details className="task-menu">
        <summary className="icon-button" aria-label={`更多操作 ${task.title}`}>
          <MoreHorizontal size={18} />
        </summary>
        <div className="dropdown-menu">
          <button
            onClick={(e) => {
              e.currentTarget.closest("details")?.removeAttribute("open");
              edit(task);
            }}
          >
            <Pencil size={14} />
            编辑任务
          </button>
          <button
            onClick={(e) => {
              e.currentTarget.closest("details")?.removeAttribute("open");
              reschedule(task);
            }}
          >
            <CalendarDays size={14} />
            重新安排日期
          </button>
          <button
            onClick={(e) => {
              e.currentTarget.closest("details")?.removeAttribute("open");
              action(task, completed || cancelled ? "reopen" : "cancel");
            }}
          >
            {completed || cancelled ? <RotateCcw size={14} /> : <X size={14} />}
            {completed || cancelled ? "重新打开" : "取消任务"}
          </button>
        </div>
      </details>
    </div>
  );
}
