import { uiText, uiFormat } from "@/lib/i18n";
import { ArrowUpRight, Flag, FolderOpen, Plus, Target } from "lucide-react";
import { dateLabel, statusLabel } from "@/lib/api";
import type {
  Bootstrap,
  EditorState,
  Progress,
  ProjectProgress,
} from "@/lib/types";

export function ProgressBar({
  value,
  color,
  className = "",
}: {
  value: number;
  color?: string;
  className?: string;
}) {
  return (
    <div className={`progress-track ${className}`}>
      <div
        style={{
          width: `${Math.max(0, Math.min(100, value || 0))}%`,
          backgroundColor: color,
        }}
      />
    </div>
  );
}
export function ProgressRing({
  value,
  size = 108,
  label,
}: {
  value: number;
  size?: number;
  label?: string;
}) {
  const radius = 43;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="progress-ring" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="6"
          className="ring-base"
        />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${circumference * (value / 100)} ${circumference}`}
          transform="rotate(-90 50 50)"
        />
      </svg>
      <div>
        <strong>
          {Math.round(value)}
          <small>%</small>
        </strong>
        {label && <span>{label}</span>}
      </div>
    </div>
  );
}

export function ProjectPath({
  project,
  color = "#acbcf7",
  compact = false,
}: {
  project: ProjectProgress;
  color?: string;
  compact?: boolean;
}) {
  const current =
    typeof project.current_milestone === "string"
      ? project.current_milestone
      : project.current_milestone?.name;
  return (
    <div className={`project-path ${compact ? "compact" : ""}`}>
      <div className="project-path-head">
        <span>
          <FolderOpen size={16} style={{ color }} />
          {project.name}
        </span>
        <span className="muted">
          {project.total
            ? `${project.completed} / ${project.total}`
            : uiText("暂无任务")}
        </span>
      </div>
      <ProgressBar value={project.percent} color={color} />
      {current && (
        <p className="current-stage">
          <Flag size={12} /> {uiText("当前阶段：")}{current}
        </p>
      )}
      {!compact && project.milestones.length > 0 && (
        <div className="milestone-path">
          {project.milestones.map((m) => (
            <div
              key={m.id}
              className={
                m.status === "completed" ||
                (m.total > 0 && m.completed === m.total)
                  ? "done"
                  : ""
              }
            >
              <i />
              <div>
                <strong>{m.name}</strong>
                <span>
                  {m.total ? uiFormat("{0}/{1} 已完成", m.completed, m.total) : uiText("暂无任务")}
                  {m.deadline ? ` · ${dateLabel(m.deadline, true)}` : ""}
                </span>
              </div>
              <span className="milestone-percent">
                {m.total ? `${Math.round(m.percent)}%` : "—"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function OverallProgress({
  progress,
  openGoals,
}: {
  progress: Progress;
  openGoals: () => void;
}) {
  const allProjects = [
    ...progress.goals.flatMap((g) =>
      g.projects.map((p) => ({ ...p, color: g.color, goal: g.name })),
    ),
    ...progress.standalone_projects.map((p) => ({
      ...p,
      color: "#acbcf7",
      goal: uiText("独立项目"),
    })),
  ].filter((p) => p.status !== "archived");
  return (
    <section className="panel overall-panel">
      <div className="panel-heading">
        <div>
          <h2>{uiText("整体进度与当前阶段")}</h2>
        </div>
        <button className="text-button" onClick={openGoals}>
          {uiText("查看全局")}
          <ArrowUpRight size={15} />
        </button>
      </div>
      {allProjects.length ? (
        <div className="overall-grid">
          {allProjects.slice(0, 4).map((p) => (
            <div className="overall-item" key={p.id}>
              <p className="overline" style={{ color: p.color }}>
                {p.goal}
              </p>
              <ProjectPath project={p} color={p.color} compact />
            </div>
          ))}
        </div>
      ) : (
        <div className="quiet-empty">
          <Target size={26} />
          <div>
            <strong>{uiText("为你的下一步，留一个位置")}</strong>
            <p>{uiText("创建目标、项目和里程碑，进度会随着真实完成记录逐步呈现。")}</p>
          </div>
          <button className="button secondary small" onClick={openGoals}>
            {uiText("建立规划")}
            <ArrowUpRight size={15} />
          </button>
        </div>
      )}
    </section>
  );
}

export function GoalsPage({
  data,
  progress,
  edit,
}: {
  data: Bootstrap;
  progress: Progress;
  edit: (value: EditorState) => void;
}) {
  return (
    <>
      <div className="section-toolbar">
        <div className="subtle-note">
          <Target size={16} />
          {uiText("目标 → 项目 → 里程碑 → 每一次完成")}
        </div>
        <div className="button-group">
          <button
            className="button secondary small"
            onClick={() => edit({ kind: "project" })}
          >
            <Plus size={15} />
            {uiText("项目")}
          </button>
          <button
            className="button secondary small"
            onClick={() => edit({ kind: "milestone" })}
            disabled={!data.projects.length}
          >
            <Plus size={15} />
            {uiText("里程碑")}
          </button>
        </div>
      </div>
      {data.goals.length === 0 && data.projects.length === 0 && (
        <div className="panel large-empty">
          <div className="empty-art">
            <Target size={34} />
            <span />
            <i />
          </div>
          <h2>{uiText("你的规划，由你定义")}</h2>
          <p>
            {uiText("一个长期目标，一两个项目，一些小的里程碑。")}
            <br />
            {uiText("从你在意的事情开始，不需要一次想好所有安排。")}
          </p>
          <button
            className="button primary"
            onClick={() => edit({ kind: "goal" })}
          >
            <Plus size={17} />
            {uiText("创建第一个目标")}
          </button>
        </div>
      )}
      <div className="goal-grid">
        {progress.goals.map((goal) => (
          <section className="panel goal-card" key={goal.id}>
            <div className="goal-card-top">
              <div
                className="goal-icon"
                style={{
                  backgroundColor: `${goal.color}14`,
                  color: goal.color,
                }}
              >
                <Target size={23} />
              </div>
              <span className={`status-pill ${goal.status}`}>
                {statusLabel(goal.status)}
              </span>
              <button
                className="text-button"
                onClick={() =>
                  edit({
                    kind: "goal",
                    item: data.goals.find((g) => g.id === goal.id),
                  })
                }
              >
                {uiText("编辑")}
                <ArrowUpRight size={14} />
              </button>
            </div>
            <h2>{goal.name}</h2>
            {data.goals.find((g) => g.id === goal.id)?.description && (
              <p className="goal-description">
                {data.goals.find((g) => g.id === goal.id)?.description}
              </p>
            )}
            <div className="goal-progress-number">
              <strong>
                {goal.total ? Math.round(goal.percent) : 0}
                <small>%</small>
              </strong>
              <span>
                {goal.total
                  ? uiFormat("{0} / {1} · 已生成任务完成率", goal.completed, goal.total)
                  : uiText("尚无任务 · 等待你的第一步")}
              </span>
            </div>
            <ProgressBar value={goal.percent} color={goal.color} />
            <div className="goal-dates">
              <span>
                {uiText("开始")}{" "}
                {data.goals.find((g) => g.id === goal.id)?.start_date ||
                  uiText("未设置")}
              </span>
              <span>
                {uiText("目标")}{" "}
                {data.goals.find((g) => g.id === goal.id)?.target_date ||
                  uiText("未设置")}
              </span>
            </div>
            <div className="goal-projects">
              {goal.projects.map((project) => (
                <div key={project.id}>
                  <ProjectPath project={project} color={goal.color} />
                  <div className="project-actions">
                    <button
                      className="text-button"
                      onClick={() =>
                        edit({
                          kind: "project",
                          item: data.projects.find((p) => p.id === project.id),
                        })
                      }
                    >
                      {uiText("编辑项目")}
                    </button>
                    <button
                      className="text-button"
                      onClick={() =>
                        edit({
                          kind: "milestone",
                          defaults: { project_id: project.id },
                        })
                      }
                    >
                      <Plus size={12} />
                      {uiText("里程碑")}
                    </button>
                    <button
                      className="text-button"
                      onClick={() =>
                        edit({
                          kind: "task",
                          defaults: { project_id: project.id },
                        })
                      }
                    >
                      <Plus size={12} />
                      {uiText("任务")}
                    </button>
                  </div>
                  {project.milestones.length > 0 && (
                    <div className="milestone-edit-list">
                      {project.milestones.map((m) => (
                        <button
                          key={m.id}
                          onClick={() =>
                            edit({
                              kind: "milestone",
                              item: data.milestones.find((x) => x.id === m.id),
                            })
                          }
                        >
                          <Flag size={11} />
                          {m.name}
                          <ArrowUpRight size={11} />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <button
              className="add-project"
              onClick={() =>
                edit({ kind: "project", defaults: { goal_id: goal.id } })
              }
            >
              <Plus size={15} />
              {uiText("添加项目")}
            </button>
          </section>
        ))}
      </div>
      {progress.standalone_projects.length > 0 && (
        <section className="panel standalone-panel">
          <div className="panel-heading">
            <div>
              <h2>{uiText("独立项目")}</h2>
            </div>
          </div>
          <div className="standalone-grid">
            {progress.standalone_projects.map((project) => (
              <div key={project.id}>
                <ProjectPath project={project} />
                <div className="project-actions">
                  <button
                    className="text-button"
                    onClick={() =>
                      edit({
                        kind: "project",
                        item: data.projects.find((p) => p.id === project.id),
                      })
                    }
                  >
                    {uiText("编辑项目")}
                  </button>
                  <button
                    className="text-button"
                    onClick={() =>
                      edit({
                        kind: "milestone",
                        defaults: { project_id: project.id },
                      })
                    }
                  >
                    <Plus size={12} />
                    {uiText("里程碑")}
                  </button>
                  <button
                    className="text-button"
                    onClick={() =>
                      edit({
                        kind: "task",
                        defaults: { project_id: project.id },
                      })
                    }
                  >
                    <Plus size={12} />
                    {uiText("任务")}
                  </button>
                </div>
                <div className="milestone-edit-list">
                  {project.milestones.map((m) => (
                    <button
                      key={m.id}
                      onClick={() =>
                        edit({
                          kind: "milestone",
                          item: data.milestones.find((x) => x.id === m.id),
                        })
                      }
                    >
                      <Flag size={11} />
                      {m.name}
                      <ArrowUpRight size={11} />
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
