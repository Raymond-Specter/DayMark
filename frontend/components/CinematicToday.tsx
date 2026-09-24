import { getLanguage, uiText, uiFormat } from "@/lib/i18n";
import type { ReactNode } from "react";
import { ArrowDown, ArrowRight, ArrowUpRight, CalendarDays, Clock3, Plus } from "lucide-react";
import "./cinematic-today.css";

type NextTask = {
  title: string;
  start_time: string | null;
  estimated_duration: number;
};

type Stage = {
  project: string;
  milestone: string;
  completed: number;
  total: number;
};

type Props = {
  dateLabel: string;
  headerActions: ReactNode;
  remainingCount: number;
  completedCount: number;
  plannedHours: string;
  activeProjectCount: number;
  dailyPercent: number;
  nextTask: NextTask | null;
  stage: Stage | null;
  onShowTasks: () => void;
  onOpenCalendar: () => void;
  onCreateTask: () => void;
  onOpenNextTask: () => void;
};

export default function CinematicToday({
  dateLabel,
  headerActions,
  remainingCount,
  completedCount,
  plannedHours,
  activeProjectCount,
  dailyPercent,
  nextTask,
  stage,
  onShowTasks,
  onOpenCalendar,
  onCreateTask,
  onOpenNextTask,
}: Props) {
  const stagePercent = stage?.total
    ? Math.min(100, Math.max(0, Math.round((stage.completed / stage.total) * 100)))
    : 0;

  return (
    <section className="cinematic-today" aria-labelledby="cinematic-today-title">
      <div className="cinematic-today__art" aria-hidden="true">
        <video autoPlay loop muted playsInline preload="metadata" poster="/images/gargantua-poster.jpg">
          <source src="/video/gargantua-background.mp4" type="video/mp4" />
        </video>
      </div>
      <div className="cinematic-today__bottom-blur" aria-hidden="true" />

      <header className="cinematic-today__top cinematic-today__enter cinematic-today__delay-0">
        <span className="cinematic-today__edition">
          <span className="cinematic-today__edition-mark" aria-hidden="true" />
          DAYMARK <span aria-hidden="true">/</span> TODAY
        </span>
        <div className="cinematic-today__header-right">
          <span className="cinematic-today__date">
            <CalendarDays size={15} aria-hidden="true" />
            {dateLabel}
          </span>
          <div className="cinematic-today__utilities">{headerActions}</div>
        </div>
      </header>

      <div className="cinematic-today__body">
        <div className="cinematic-today__copy">
          <div className="cinematic-today__eyebrow cinematic-today__enter cinematic-today__delay-1">
            <span className="cinematic-today__live-dot" aria-hidden="true" />
            {uiText("今日进度")} <span className="cinematic-today__eyebrow-rule" aria-hidden="true" />
            <strong>{dailyPercent}%</strong> {uiText("已完成")}
          </div>
          <h1 id="cinematic-today-title" className="cinematic-today__title cinematic-today__enter cinematic-today__delay-2">
            {remainingCount > 0 ? (
              <>
                {uiText("今天，")}<br /><span>{getLanguage() === "en" ? `${remainingCount} ${remainingCount === 1 ? "task" : "tasks"} left.` : `还有 ${remainingCount} 件事。`}</span>
              </>
            ) : completedCount > 0 ? (
              <>
                {getLanguage() === "en" ? "Today," : "今天的计划，"}<br /><span>{getLanguage() === "en" ? "all done." : "已完成。"}</span>
              </>
            ) : (
              <>
                {uiText("今天，")}<br /><span>{uiText("从一件事开始。")}</span>
              </>
            )}
          </h1>
          <div className="cinematic-today__actions cinematic-today__enter cinematic-today__delay-4">
            <button type="button" className="cinematic-today__primary" onClick={onShowTasks}>
              {uiText("查看今日任务")} <ArrowRight size={18} aria-hidden="true" />
            </button>
            <button type="button" className="cinematic-today__glass cinematic-today__secondary" onClick={onOpenCalendar}>
              <CalendarDays size={17} aria-hidden="true" /> {uiText("打开日历")}
            </button>
          </div>
        </div>

        <aside className="cinematic-today__cards" aria-label={uiText("接下来的安排与当前阶段")}>
          <div className="cinematic-today__card cinematic-today__enter cinematic-today__delay-5">
            <div className="cinematic-today__card-top">
              <span>{uiText("下一项")} <span className="cinematic-today__card-index">01</span></span>
              <Clock3 size={17} aria-hidden="true" />
            </div>
            {nextTask ? (
              <>
                <span className="cinematic-today__card-time">
                  {nextTask.start_time || uiText("时间待定")}
                  {nextTask.estimated_duration > 0 && <span> · {nextTask.estimated_duration} {uiText("分钟")}</span>}
                </span>
                <h2 title={nextTask.title}>{nextTask.title}</h2>
                <button type="button" className="cinematic-today__card-link" onClick={onOpenNextTask}>
                  {uiText("打开任务")} <ArrowUpRight size={15} aria-hidden="true" />
                </button>
              </>
            ) : (
              <>
                <h2>{remainingCount > 0 ? uiText("等待前置任务") : uiText("暂时没有下一项")}</h2>
                <button type="button" className="cinematic-today__card-link" onClick={onCreateTask}>
                  <Plus size={15} aria-hidden="true" /> {uiText("添加任务")}
                </button>
              </>
            )}
          </div>

          <div className="cinematic-today__card cinematic-today__stage cinematic-today__enter cinematic-today__delay-6">
            <div className="cinematic-today__card-top">
              <span>{uiText("当前阶段")} <span className="cinematic-today__card-index">02</span></span>
              <span className="cinematic-today__stage-percent">{stage ? `${stagePercent}%` : "—"}</span>
            </div>
            <span className="cinematic-today__stage-project">{stage?.project || uiText("尚无进行中项目")}</span>
            <h2 title={stage?.milestone || ""}>{stage?.milestone || uiText("阶段待设置")}</h2>
            {stage && (
              <div
                className="cinematic-today__stage-track"
                role="progressbar"
                aria-label={uiText("当前项目任务完成率")}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={stagePercent}
              >
                <span style={{ width: `${stagePercent}%` }} />
              </div>
            )}
            <span className="cinematic-today__stage-count">
              {stage ? uiFormat("{0} / {1} 项任务完成", stage.completed, stage.total) : uiText("添加项目后会显示当前阶段")}
            </span>
          </div>
        </aside>
      </div>

      <footer className="cinematic-today__footer cinematic-today__enter cinematic-today__delay-7">
        <div className="cinematic-today__metrics" aria-label={uiText("今日计划概览")}>
          <div className="cinematic-today__metric">
            <strong>{remainingCount}</strong><span>{uiText("待完成")}</span>
          </div>
          <div className="cinematic-today__metric">
            <strong>{completedCount}</strong><span>{uiText("已完成")}</span>
          </div>
          <div className="cinematic-today__metric">
            <strong>{plannedHours}<small> h</small></strong><span>{uiText("计划时长")}</span>
          </div>
          <div className="cinematic-today__metric">
            <strong>{activeProjectCount}</strong><span>{uiText("进行中项目")}</span>
          </div>
        </div>
        <button type="button" className="cinematic-today__scroll" onClick={onShowTasks}>
          {uiText("向下查看今日安排")} <ArrowDown size={15} aria-hidden="true" />
        </button>
      </footer>
    </section>
  );
}
