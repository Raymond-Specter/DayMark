import { getLanguage, uiText } from "@/lib/i18n";
import type { ReactNode } from "react";
import type { Theme } from "@/lib/theme";
import { ArrowDown, ArrowRight, CalendarDays } from "lucide-react";
import "./cinematic-today.css";

type Props = {
  theme: Theme;
  dateLabel: string;
  headerActions: ReactNode;
  remainingCount: number;
  completedCount: number;
  plannedHours: string;
  activeProjectCount: number;
  dailyPercent: number;
  onShowTasks: () => void;
  onOpenCalendar: () => void;
};

export default function CinematicToday({
  theme,
  dateLabel,
  headerActions,
  remainingCount,
  completedCount,
  plannedHours,
  activeProjectCount,
  dailyPercent,
  onShowTasks,
  onOpenCalendar,
}: Props) {
  return (
    <section className="cinematic-today" aria-labelledby="cinematic-today-title">
      <div className="cinematic-today__art" aria-hidden="true">
        {theme === "dark" && <video autoPlay loop muted playsInline preload="metadata" poster="/images/gargantua-poster.jpg">
          <source src="/video/gargantua-background.mp4" type="video/mp4" />
        </video>}
      </div>
      {theme === "pink" && <svg className="cinematic-today__flower" viewBox="0 0 400 400" aria-hidden="true">
        <g fill="#f3bed0" stroke="#fff9fc" strokeWidth="3">
          {[0, 60, 120, 180, 240, 300].map((angle) => <ellipse key={angle} cx="200" cy="118" rx="61" ry="95" transform={`rotate(${angle} 200 200)`} />)}
          <circle cx="200" cy="200" r="48" fill="#fff2c9" />
        </g>
      </svg>}
      {(theme === "morandi" || theme === "mist") && <svg className={`cinematic-today__flower ${theme === "mist" ? "mist-art" : "morandi-art"}`} viewBox="0 0 400 400" aria-hidden="true">
        <rect x="145" y="30" width="170" height="270" rx="85" fill={theme === "mist" ? "#afd8e4" : "#a6b3a5"} />
        <circle cx="142" cy="268" r="100" fill={theme === "mist" ? "#f5c6c3" : "#c4a599"} />
        <ellipse cx="234" cy="331" rx="132" ry="40" fill={theme === "mist" ? "#dce8e5" : "#d6ccba"} />
        <path d="M233 79v168" stroke={theme === "mist" ? "#f9fbfc" : "#f5f2ed"} strokeWidth="2" fill="none" />
      </svg>}
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
