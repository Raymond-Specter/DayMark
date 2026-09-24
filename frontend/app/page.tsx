"use client";
import { loadLanguage, saveLanguage, uiText, uiFormat, type Language } from "@/lib/i18n";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  Clock3,
  Flag,
  LayoutGrid,
  Leaf,
  LibraryBig,
  ListTodo,
  LoaderCircle,
  Menu,
  Plus,
  RefreshCw,
  Repeat2,
  Search,
  Settings,
  Sparkles,
  BookOpenCheck,
  Sun,
  Target,
  X,
} from "lucide-react";
import { api, dateLabel, deadlineLabel, hours, send } from "@/lib/api";
import type {
  AppNotification,
  Bootstrap,
  EditorState,
  Progress,
  Routine,
  Statistics,
  Task,
  TodayData,
} from "@/lib/types";
import Editor from "@/components/Editor";
import TaskRow, { type TaskAction } from "@/components/TaskRow";
import {
  GoalsPage,
  OverallProgress,
} from "@/components/Progress";
import CinematicToday from "@/components/CinematicToday";
import { Dashboard, DailyReview, SettingsPage } from "@/components/Insights";
const Assistant = dynamic(() => import("@/components/assistant/Assistant"), {
  ssr: false,
});
const CalendarView = dynamic(() => import("@/components/CalendarView"), {
  ssr: false,
  loading: () => <div className="panel loading-panel">{uiText("正在加载日历…")}</div>,
});
const LearningArchive = dynamic(() => import("@/components/LearningArchive"), {
  ssr: false,
});
const KnowledgeBase = dynamic(() => import("@/components/KnowledgeBase"), {
  ssr: false,
});

type Page =
  | "today"
  | "calendar"
  | "tasks"
  | "goals"
  | "routines"
  | "learning"
  | "knowledge"
  | "review"
  | "dashboard"
  | "assistant"
  | "settings";
const pages: {
  id: Page;
  title: string;
  icon: typeof Sun;
}[] = [
  {
    id: "today",
    title: "今日概览",
    icon: Sun,
  },
  {
    id: "calendar",
    title: "我的日历",
    icon: CalendarDays,
  },
  {
    id: "tasks",
    title: "全部任务",
    icon: ListTodo,
  },
  {
    id: "goals",
    title: "目标与项目",
    icon: Target,
  },
  {
    id: "routines",
    title: "重复任务",
    icon: Repeat2,
  },
  {
    id: "learning",
    title: "学习档案",
    icon: BookOpenCheck,
  },
  {
    id: "knowledge",
    title: "知识库",
    icon: LibraryBig,
  },
  {
    id: "review",
    title: "每日复盘",
    icon: Leaf,
  },
  {
    id: "dashboard",
    title: "数据统计",
    icon: BarChart3,
  },
  {
    id: "assistant",
    title: "AI Assistant",
    icon: Sparkles,
  },
  {
    id: "settings",
    title: "偏好设置",
    icon: Settings,
  },
];
function weekRange(today: string) {
  const date = new Date(`${today}T12:00:00`);
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  const start = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  return { start, end: today };
}
const emptyProgress: Progress = {
  goals: [],
  standalone_projects: [],
  unassigned_tasks: 0,
};

export default function Home() {
  const [page, setPage] = useState<Page>("today");
  const [language, setLanguageState] = useState<Language>("en");
  const [mobileNav, setMobileNav] = useState(false);
  const [data, setData] = useState<Bootstrap | null>(null);
  const [today, setToday] = useState<TodayData | null>(null);
  const [progress, setProgress] = useState<Progress>(emptyProgress);
  const [stats, setStats] = useState<Statistics | null>(null);
  const [range, setRange] = useState<{ start: string; end: string } | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [rescheduleTask, setRescheduleTask] = useState<Task | null>(null);
  const [busyTask, setBusyTask] = useState("");
  const [revision, setRevision] = useState(0);
  const [toast, setToast] = useState<{
    message: string;
    error: boolean;
  } | null>(null);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [projectFilter, setProjectFilter] = useState("all");
  const [taskDate, setTaskDate] = useState("");
  const [showCompleted, setShowCompleted] = useState(false);
  const rangeRef = useRef(range);
  rangeRef.current = range;
  const knownNotifications = useRef(new Set<string>());
  const todayRef = useRef("");
  const notify = useCallback(
    (message: string, error = false) => setToast({ message, error }),
    [],
  );
  useEffect(() => {
    if (!toast) return;
    const timeout = setTimeout(() => setToast(null), toast.error ? 9000 : 4000);
    return () => clearTimeout(timeout);
  }, [toast]);
  const refresh = useCallback(async () => {
    const bootstrap = await api<Bootstrap>("/bootstrap");
    const activeRange = rangeRef.current || weekRange(bootstrap.today);
    const [todayResult, statsResult, progressResult] = await Promise.all([
      api<TodayData>("/today"),
      api<Statistics>(
        `/statistics?start=${activeRange.start}&end=${activeRange.end}`,
      ),
      api<Progress>("/progress"),
    ]);
    setData(bootstrap);
    setToday(todayResult);
    setStats(statsResult);
    setProgress(progressResult);
    setRange((r) => r || activeRange);
    todayRef.current = bootstrap.today;
    setRevision((n) => n + 1);
    setLoadError("");
  }, []);
  const initialize = useCallback(async () => {
    setLoading(true);
    try {
      await send("/scheduler/sync", {});
      await send("/reminders/dispatch", {});
      await refresh();
    } catch (e) {
      setLoadError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [refresh]);
  useEffect(() => {
    initialize();
  }, [initialize]);
  useEffect(() => {
    setLanguageState(loadLanguage());
  }, []);
  useEffect(() => {
    const hash =
      window.location.hash.slice(1) ||
      (window.location.pathname === "/assistant" ? "assistant" : "today");
    if (pages.some((p) => p.id === hash)) setPage(hash as Page);
    const handler = () => {
      const next = window.location.hash.slice(1);
      if (pages.some((p) => p.id === next)) setPage(next as Page);
    };
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  useEffect(() => {
    if (!range) return;
    let active = true;
    api<Statistics>(`/statistics?start=${range.start}&end=${range.end}`)
      .then((result) => {
        if (active) setStats(result);
      })
      .catch((e) => notify(e.message, true));
    return () => {
      active = false;
    };
  }, [range, notify]);
  useEffect(() => {
    if (!data) return;
    let stopped = false;
    async function poll() {
      try {
        await send("/reminders/dispatch", {});
        const notifications = await api<AppNotification[]>("/notifications");
        if (stopped) return;
        setData((old) => (old ? { ...old, notifications } : old));
        for (const item of notifications) {
          if (!item.read_at && !knownNotifications.current.has(item.id)) {
            knownNotifications.current.add(item.id);
            if (
              "Notification" in window &&
              Notification.permission === "granted"
            )
              new Notification(uiText("Daymark · 任务提醒"), {
                body: item.title,
                tag: item.id,
              });
          }
        }
        const current = new Intl.DateTimeFormat("sv-SE", {
          timeZone: data!.settings.timezone,
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
        }).format(new Date());
        if (current !== todayRef.current) {
          await send("/scheduler/sync", {});
          await refresh();
        }
      } catch {
        /* Polling retries. Explicit mutations and refresh surface errors. */
      }
    }
    const timer = setInterval(poll, 30000);
    const focus = () => {
      void poll();
    };
    window.addEventListener("focus", focus);
    return () => {
      stopped = true;
      clearInterval(timer);
      window.removeEventListener("focus", focus);
    };
  }, [data?.settings.timezone, refresh, Boolean(data)]);
  function navigate(next: Page) {
    setPage(next);
    setMobileNav(false);
    window.location.hash = next;
    setNotificationOpen(false);
  }
  function changeLanguage(next: Language) {
    saveLanguage(next);
    setLanguageState(next);
  }
  async function saved(message: string) {
    await refresh();
    notify(message);
  }
  async function taskAction(task: Task, action: TaskAction, date?: string) {
    setBusyTask(task.id);
    try {
      await send(`/tasks/${task.id}/actions`, {
        action,
        version: task.version,
        ...(date ? { date } : {}),
      });
      await refresh();
      notify(
        {
          complete: uiText("完成记录已保存，向前一步。"),
          reopen: uiText("任务已重新打开"),
          reschedule: uiText("任务已重新安排"),
          cancel: uiText("任务已取消"),
          keep_overdue: uiText("已保留逾期状态"),
        }[action],
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusyTask("");
    }
  }
  const editTask = (task: Task) => setEditor({ kind: "task", item: task });
  const currentPage = pages.find((p) => p.id === page)!;
  const remaining =
    today?.tasks.filter(
      (t) => !["completed", "cancelled"].includes(t.status),
    ) || [];
  const complete = today?.tasks.filter((t) => t.status === "completed") || [];
  const timedTasks = remaining.filter((t) => t.start_time);
  const nextTask = remaining.find((t) => !t.blocked);
  const activeProjects = [
    ...progress.goals.flatMap((g) =>
      g.projects.map((p) => ({ ...p, color: g.color })),
    ),
    ...progress.standalone_projects.map((p) => ({ ...p, color: "#acbcf7" })),
  ].filter((p) => !["completed", "archived"].includes(p.status));
  const dailyPercent =
    remaining.length + complete.length
      ? Math.round(
          (complete.length / (remaining.length + complete.length)) * 100,
        )
      : 0;
  const plannedMinutes =
    today?.tasks
      .filter((t) => t.status !== "cancelled")
      .reduce((sum, t) => sum + t.estimated_duration, 0) || 0;
  const unread = data?.notifications.filter((n) => !n.read_at).length || 0;
  const filteredTasks =
    data?.tasks
      .filter(
        (t) =>
          (statusFilter === "all" ||
            (statusFilter === "open"
              ? !["completed", "cancelled"].includes(t.status)
              : t.status === statusFilter)) &&
          (projectFilter === "all" ||
            t.project_id === projectFilter ||
            (projectFilter === "none" && !t.project_id)) &&
          (!taskDate || t.date === taskDate) &&
          `${t.title} ${t.description}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      )
      .sort(
        (a, b) =>
          (a.date || "9999").localeCompare(b.date || "9999") ||
          (a.start_time || "99:99").localeCompare(b.start_time || "99:99") ||
          a.priority - b.priority,
      ) || [];
  const row = (
    t: Task,
    options: { showDate?: boolean; overdueActions?: boolean } = {},
  ) => (
    <TaskRow
      key={t.id}
      task={t}
      data={data!}
      action={taskAction}
      edit={editTask}
      reschedule={setRescheduleTask}
      busy={busyTask === t.id}
      {...options}
    />
  );

  const utilityActions = (
    <>
      <button
        className="icon-button"
        title={uiText("刷新数据")}
        aria-label={uiText("刷新数据")}
        disabled={loading}
        onClick={async () => {
          try {
            await send("/scheduler/sync", {});
            await refresh();
            notify(uiText("数据已同步"));
          } catch (e) {
            notify((e as Error).message, true);
          }
        }}
      >
        <RefreshCw size={17} />
      </button>
      <div className="notification-anchor">
        <button
          className={`icon-button notification-button ${notificationOpen ? "selected" : ""}`}
          aria-label={uiFormat("提醒通知{0}", unread ? uiFormat("，{0} 条未读", unread) : "")}
          onClick={() => setNotificationOpen(!notificationOpen)}
        >
          <Bell size={19} />
          {unread > 0 && <i />}
        </button>
        {notificationOpen && (
          <section className="notification-popover">
            <div>
              <h3>{uiText("提醒中心")}</h3>
              <span>{unread} {uiText("条未读")}</span>
            </div>
            {data?.notifications.length ? (
              data.notifications.slice(0, 30).map((n) => (
                <button
                  key={n.id}
                  className={n.read_at ? "read" : ""}
                  onClick={async () => {
                    try {
                      await send(`/notifications/${n.id}/read`, {});
                      await refresh();
                      const task = data.tasks.find(
                        (t) => t.id === n.task_id,
                      );
                      if (task) editTask(task);
                      setNotificationOpen(false);
                    } catch (e) {
                      notify((e as Error).message, true);
                    }
                  }}
                >
                  <span className="notification-dot" />
                  <div>
                    <strong>{n.title}</strong>
                    <p>{deadlineLabel(n.due_at, data.settings.timezone)}</p>
                  </div>
                </button>
              ))
            ) : (
              <div className="notification-empty">
                <Bell size={25} />
                <p>
                  {uiText("还没有提醒")}
                  <br />
                  <small>{uiText("可为任务或重复规则设置提醒。")}</small>
                </p>
              </div>
            )}
          </section>
        )}
      </div>
      <div className="topbar-avatar">M</div>
    </>
  );

  return (
    <div className="app-shell">
      {mobileNav && (
        <button
          className="sidebar-overlay"
          aria-label={uiText("关闭导航")}
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside className={`sidebar ${mobileNav ? "mobile-open" : ""}`}>
        <a className="brand" href="#today" onClick={() => navigate("today")}>
          <div className="brand-mark">
            <span />
            <span />
            <span />
          </div>
          <span>
            daymark<span className="brand-period">.</span>
          </span>
        </a>
        <div className="workspace-switch">
          <div className="workspace-avatar">P</div>
          <div>
            <strong>{uiText("个人规划空间")}</strong>
          </div>
          <ChevronRight size={15} />
        </div>
        <span className="nav-caption">{uiText("你的每一天")}</span>
        <nav aria-label={uiText("主要导航")}>
          {pages.slice(0, 3).map((p) => (
            <button
              key={p.id}
              onClick={() => navigate(p.id)}
              className={page === p.id ? "active" : ""}
            >
              <p.icon size={19} />
              <span>{uiText(p.title)}</span>
              {p.id === "today" && remaining.length > 0 && (
                <i>{remaining.length}</i>
              )}
            </button>
          ))}
          {[
            { label: uiText("规划"), items: pages.slice(3, 5) },
            { label: uiText("知识与回顾"), items: pages.slice(5, 9) },
            { label: uiText("智能工作台"), items: pages.slice(9, 10) },
          ].map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-caption second">{group.label}</span>
              {group.items.map((p) => (
                <button
                  key={p.id}
                  onClick={() => navigate(p.id)}
                  className={page === p.id ? "active" : ""}
                >
                  <p.icon size={19} />
                  <span>{uiText(p.title)}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            className={`settings-nav ${page === "settings" ? "active" : ""}`}
            onClick={() => navigate("settings")}
          >
            <Settings size={18} />
            {uiText("偏好设置")}
          </button>
          <div className="profile">
            <div className="profile-avatar">ME</div>
            <div>
              <strong>{uiText("我的空间")}</strong>
              <span>
                <i />
                {uiText("本地存储 · 私人规划")}
              </span>
            </div>
          </div>
        </div>
      </aside>
      <main className="main-workspace">
        {(page !== "today" || !data || !today || !stats || Boolean(loadError)) && <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label={uiText("打开导航")}
              onClick={() => setMobileNav(true)}
            >
              <Menu size={22} />
            </button>
            <span>{uiText("工作空间")}</span>
            <ChevronRight size={13} />
            <strong>{uiText(currentPage.title)}</strong>
          </div>
          <div className="topbar-actions">
            <span className="today-chip">
              <CalendarDays size={14} />
              {data?.today ? dateLabel(data.today) : uiText("你的个人规划系统")}
            </span>
            {utilityActions}
          </div>
        </header>}
        <div className={`page-content page-${page}`}>
          <div className="page-heading">
            <div>
              <div className="page-title-line">
                <h1>{uiText(currentPage.title)}</h1>
              </div>
            </div>
            {![
              "review",
              "dashboard",
              "settings",
              "assistant",
              "learning",
              "knowledge",
            ].includes(
              page,
            ) && (
              <button
                className="button primary"
                disabled={!data}
                onClick={() =>
                  setEditor({
                    kind:
                      page === "goals"
                        ? "goal"
                        : page === "routines"
                          ? "routine"
                          : "task",
                  })
                }
              >
                <Plus size={18} />
                {page === "goals"
                  ? uiText("新建目标")
                  : page === "routines"
                    ? uiText("新建重复任务")
                    : uiText("新建任务")}
              </button>
            )}
          </div>
          {page === "assistant" ? (
            <Assistant changed={() => void refresh()} />
          ) : loading ? (
            <div className="panel loading-panel">
              <LoaderCircle className="spin" size={28} />
              <h2>{uiText("正在准备你的规划空间")}</h2>
              <p>{uiText("同步日历、任务与完成记录…")}</p>
            </div>
          ) : loadError || !data || !today || !stats ? (
            <div className="panel large-empty">
              <CircleHelp size={36} />
              <h2>{uiText("暂时无法连接规划服务")}</h2>
              <p>{loadError || uiText("请确认后端服务已启动。")}</p>
              <button className="button primary" onClick={initialize}>
                <RefreshCw size={16} />
                {uiText("重新连接")}
              </button>
            </div>
          ) : (
            <>
              {page === "today" && (
                <>
                  <CinematicToday
                    dateLabel={dateLabel(data.today)}
                    headerActions={<>
                      <button className="icon-button mobile-menu" aria-label={uiText("打开导航")} onClick={() => setMobileNav(true)}>
                        <Menu size={22} />
                      </button>
                      {utilityActions}
                    </>}
                    remainingCount={remaining.length}
                    completedCount={complete.length}
                    plannedHours={String(hours(plannedMinutes))}
                    activeProjectCount={activeProjects.length}
                    dailyPercent={dailyPercent}
                    onShowTasks={() =>
                      document.getElementById("today-plan")?.scrollIntoView({
                        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
                          ? "auto"
                          : "smooth",
                      })
                    }
                    onOpenCalendar={() => navigate("calendar")}
                  />
                  <div className="today-after-hero">
                  {activeProjects.length > 0 && <section className="phase-strip">
                    <Flag size={18} />
                    <div className="phase-strip-label">
                      <strong>{uiText("当前阶段")}</strong>
                    </div>
                    <div className="phase-items">
                      {activeProjects.slice(0, 3).map((p) => (
                          <button key={p.id} onClick={() => navigate("goals")}>
                            <i style={{ background: p.color }} />
                            <div>
                              <strong>{p.name}</strong>
                              <span>
                                {typeof p.current_milestone === "string"
                                  ? p.current_milestone
                                  : p.current_milestone?.name ||
                                    (p.total
                                      ? uiText("已生成任务全部完成")
                                      : uiText("待设置里程碑"))}
                              </span>
                            </div>
                            <small>
                              {p.completed}/{p.total}
                            </small>
                          </button>
                        ))}
                    </div>
                    <button
                      className="text-button"
                      onClick={() => navigate("goals")}
                    >
                      {uiText("查看全局")}
                      <ArrowUpRight size={14} />
                    </button>
                  </section>}
                  <div className="today-layout" id="today-plan">
                    <div className="today-main">
                      <section className="panel today-tasks-panel">
                        <div className="panel-heading">
                          <div className="heading-with-icon">
                            <div className="section-icon">
                              <ListTodo size={19} />
                            </div>
                            <h2>{uiText("今天要做什么")}</h2>
                            <span className="count-pill">
                              {remaining.length}
                            </span>
                          </div>
                        </div>
                        {remaining.length ? (
                          <div className="today-timeline">
                            {remaining.map((t, i) => (
                              <div className="timeline-entry" key={t.id}>
                                <div className="timeline-time">
                                  <strong>{t.start_time || uiText("待定")}</strong>
                                  <span>
                                    {t.end_time ||
                                      `${t.estimated_duration} min`}
                                  </span>
                                  <i className={i === 0 ? "first" : ""} />
                                </div>
                                {row(t)}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="today-empty">
                            <div className="empty-calendar">
                              <CalendarDays size={30} />
                              <span>
                                <Check size={12} />
                              </span>
                            </div>
                            <h3>
                              {complete.length
                                ? uiText("今天的任务都完成了")
                                : uiText("今天还没有安排")}
                            </h3>
                            <p>
                              {complete.length
                                ? uiText("去每日复盘中记录一下今天的投入和感受吧。")
                                : uiText("添加一个任务，或创建会自动出现的重复任务。")}
                            </p>
                            <button
                              className="button secondary"
                              onClick={() =>
                                complete.length
                                  ? navigate("review")
                                  : setEditor({ kind: "task" })
                              }
                            >
                              {complete.length ? (
                                <Leaf size={16} />
                              ) : (
                                <Plus size={16} />
                              )}
                              {complete.length
                                ? uiText("记录今天")
                                : uiText("添加今天的第一件事")}
                            </button>
                          </div>
                        )}
                        <div className="completed-toggle">
                          <button
                            onClick={() => setShowCompleted(!showCompleted)}
                          >
                            <CheckCheck size={16} />
                            {uiText("已完成任务")}<span>{complete.length}</span>
                            <ChevronRight
                              size={15}
                              className={showCompleted ? "rotated" : ""}
                            />
                          </button>
                          {showCompleted &&
                            (complete.length ? (
                              complete.map((t) => row(t))
                            ) : (
                              <p className="empty-line">
                                {uiText("完成一件任务后，记录会出现在这里。")}
                              </p>
                            ))}
                        </div>
                      </section>
                      {today.unfinished_yesterday.length > 0 && (
                        <section className="panel yesterday-panel">
                          <div className="panel-heading">
                            <h2>
                              {uiText("昨天未完成的事")}{" "}
                              <span className="count-pill">
                                {today.unfinished_yesterday.length}
                              </span>
                            </h2>
                          </div>
                          {today.unfinished_yesterday.map((t) =>
                            row(t, { overdueActions: true }),
                          )}
                        </section>
                      )}
                      {today.overdue.filter(
                        (t) =>
                          !today.unfinished_yesterday.some(
                            (y) => y.id === t.id,
                          ) && t.date !== today.date,
                      ).length > 0 && (
                        <section className="panel overdue-panel">
                          <div className="panel-heading">
                            <h2>{uiText("更早的待处理事项")}</h2>
                            <span className="status-pill overdue">
                              {uiText("需要你的决定")}
                            </span>
                          </div>
                          {today.overdue
                            .filter(
                              (t) =>
                                !today.unfinished_yesterday.some(
                                  (y) => y.id === t.id,
                                ) && t.date !== today.date,
                            )
                            .map((t) =>
                              row(t, { showDate: true, overdueActions: true }),
                            )}
                        </section>
                      )}
                    </div>
                    <aside className="today-aside">
                      <section className="focus-card">
                        <div className="focus-label">
                          <span>
                            <span className="focus-dot" />
                            {uiText("下一项")}
                          </span>
                          <Flag size={15} />
                        </div>
                        <h3>
                          {nextTask ? uiText("从这一件开始") : uiText("为今天留一点方向")}
                        </h3>
                        {nextTask ? (
                          <>
                            <h2>{nextTask.title}</h2>
                            <p>
                              {nextTask.start_time || uiText("时间待定")} <span>·</span>{" "}
                              {nextTask.estimated_duration} {uiText("分钟")}
                            </p>
                            {data.projects.find(
                              (p) => p.id === nextTask.project_id,
                            ) && (
                              <span className="focus-project">
                                {
                                  data.projects.find(
                                    (p) => p.id === nextTask.project_id,
                                  )?.name
                                }
                              </span>
                            )}
                            <button onClick={() => editTask(nextTask)}>
                              {uiText("查看任务")}
                              <ArrowRight size={16} />
                            </button>
                          </>
                        ) : (
                          <>
                            <p>
                              {remaining.length
                                ? uiText("当前任务正在等待前置任务完成。可先检查依赖关系。")
                                : uiText("从一个小而具体的行动开始，慢慢建立你的节奏。")}
                            </p>
                            <button onClick={() => setEditor({ kind: "task" })}>
                              {uiText("添加一个行动")}
                              <Plus size={16} />
                            </button>
                          </>
                        )}
                      </section>
                      <section className="panel day-map">
                        <div className="panel-heading">
                          <div>
                            <h2>{uiText("今日时间表")}</h2>
                          </div>
                          <Clock3 size={17} />
                        </div>
                        {timedTasks.length ? (
                          <div className="day-map-list">
                            {timedTasks.slice(0, 4).map((t) => (
                              <button
                                className={t.id === nextTask?.id ? "next" : ""}
                                key={t.id}
                                onClick={() => editTask(t)}
                              >
                                <time>{t.start_time}</time>
                                <span>
                                  {t.title}
                                  <small>{t.end_time || uiFormat("{0} 分钟", t.estimated_duration)}</small>
                                </span>
                              </button>
                            ))}
                            {timedTasks.length > 4 && (
                              <span className="day-map-more">
                                {uiText("还有")} {timedTasks.length - 4} {uiText("项 · 在日历中查看")}
                              </span>
                            )}
                          </div>
                        ) : (
                          <p className="day-map-empty">{uiText("今天没有设定具体时间的任务。")}</p>
                        )}
                        <button
                          className="day-map-link"
                          onClick={() => navigate("calendar")}
                        >
                          {uiText("查看完整日历")} <ArrowUpRight size={14} />
                        </button>
                      </section>
                      <section className="panel deadlines-panel">
                        <div className="panel-heading">
                          <h2>{uiText("即将到期")}</h2>
                          <Clock3 size={17} />
                        </div>
                        {today.upcoming_deadlines.length ? (
                          today.upcoming_deadlines.slice(0, 5).map((t) => (
                            <button
                              key={t.id}
                              className="deadline-mini"
                              onClick={() => editTask(t)}
                            >
                              <span className={`priority-dot p${t.priority}`} />
                              <div>
                                <strong>{t.title}</strong>
                                <span>
                                  {deadlineLabel(
                                    t.deadline!,
                                    data.settings.timezone,
                                  )}
                                </span>
                              </div>
                              <ChevronRight size={14} />
                            </button>
                          ))
                        ) : (
                          <div className="deadlines-empty">
                            <div className="horizon-lines">
                              <i />
                              <i />
                              <i />
                            </div>
                            <p>{uiText("暂时没有临近的截止事项")}</p>
                          </div>
                        )}
                      </section>
                      <button
                        className="review-prompt"
                        onClick={() => navigate("review")}
                      >
                        <div>
                          <Leaf size={20} />
                          <span>
                            {uiText("给今天一个小小的回望")}<strong>{uiText("写每日复盘")}</strong>
                          </span>
                        </div>
                        <ArrowUpRight size={18} />
                      </button>
                    </aside>
                  </div>
                  <OverallProgress
                    progress={progress}
                    openGoals={() => navigate("goals")}
                  />
                  </div>
                </>
              )}
              {page === "calendar" && (
                <CalendarView
                  data={data}
                  revision={revision}
                  edit={setEditor}
                  changed={refresh}
                  notify={notify}
                />
              )}
              {page === "goals" && (
                <GoalsPage data={data} progress={progress} edit={setEditor} />
              )}
              {page === "tasks" && (
                <>
                  <div className="task-filters panel">
                    <label className="search-input">
                      <Search size={16} />
                      <input
                        aria-label={uiText("搜索任务")}
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder={uiText("搜索任务名称或备注…")}
                      />
                    </label>
                    <label>
                      <span className="sr-only">{uiText("任务状态")}</span>
                      <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                      >
                        <option value="all">{uiText("全部状态")}</option>
                        <option value="open">{uiText("未完成")}</option>
                        <option value="pending">{uiText("待完成")}</option>
                        <option value="completed">{uiText("已完成")}</option>
                        <option value="overdue">{uiText("已逾期")}</option>
                        <option value="rescheduled">{uiText("已改期")}</option>
                        <option value="cancelled">{uiText("已取消")}</option>
                      </select>
                    </label>
                    <label>
                      <span className="sr-only">{uiText("所属项目筛选")}</span>
                      <select
                        value={projectFilter}
                        onChange={(e) => setProjectFilter(e.target.value)}
                      >
                        <option value="all">{uiText("全部项目")}</option>
                        <option value="none">{uiText("独立任务")}</option>
                        {data.projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span className="sr-only">{uiText("计划日期筛选")}</span>
                      <input
                        type="date"
                        value={taskDate}
                        onInput={(e) => setTaskDate(e.currentTarget.value)}
                        onChange={(e) => setTaskDate(e.target.value)}
                      />
                    </label>
                    {(query ||
                      statusFilter !== "all" ||
                      projectFilter !== "all" ||
                      taskDate) && (
                      <button
                        className="text-button"
                        onClick={() => {
                          setQuery("");
                          setStatusFilter("all");
                          setProjectFilter("all");
                          setTaskDate("");
                        }}
                      >
                        {uiText("清除")}
                      </button>
                    )}
                  </div>
                  <section className="panel all-tasks-panel">
                    <div className="panel-heading">
                      <h2>
                        {uiText("任务清单")}{" "}
                        <span className="count-pill">
                          {filteredTasks.length}
                        </span>
                      </h2>
                    </div>
                    {filteredTasks.length ? (
                      filteredTasks.map((t) => row(t, { showDate: true }))
                    ) : (
                      <div className="large-empty">
                        <ListTodo size={35} />
                        <h2>
                          {data.tasks.length
                            ? uiText("没有匹配的任务")
                            : uiText("从一件小事开始")}
                        </h2>
                        <p>
                          {data.tasks.length
                            ? uiText("试试调整搜索词或筛选条件。")
                            : uiText("把想做的事情放进这里，再慢慢安排时间。")}
                        </p>
                        {!data.tasks.length && (
                          <button
                            className="button primary"
                            onClick={() => setEditor({ kind: "task" })}
                          >
                            <Plus size={16} />
                            {uiText("创建任务")}
                          </button>
                        )}
                      </div>
                    )}
                  </section>
                </>
              )}
              {page === "routines" && (
                <>
                  <div className="routine-intro">
                    <Repeat2 size={20} />
                    <p>
                      {uiText("设定一次规则，让任务按节奏出现。所有任务仍可单独调整，完成记录会一直保留。")}
                    </p>
                    <span>
                      {data.routines.filter((r) => r.active).length} {uiText("条启用中")}
                    </span>
                  </div>
                  {data.routines.length ? (
                    <div className="routine-grid">
                      {data.routines.map((r) => (
                        <RoutineCard
                          key={r.id}
                          routine={r}
                          data={data}
                          edit={() => setEditor({ kind: "routine", item: r })}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="panel large-empty">
                      <div className="empty-art">
                        <Repeat2 size={34} />
                        <span />
                        <i />
                      </div>
                      <h2>{uiText("给坚持，一个自动开始的方式")}</h2>
                      <p>
                        {uiText("每天、每周，或你自己的节奏。")}
                        <br />
                        {uiText("创建重复规则，系统会自动生成对应的任务。")}
                      </p>
                      <button
                        className="button primary"
                        onClick={() => setEditor({ kind: "routine" })}
                      >
                        <Plus size={16} />
                        {uiText("创建重复任务")}
                      </button>
                    </div>
                  )}
                </>
              )}
              {page === "learning" && (
                <LearningArchive
                  projects={data.projects}
                  today={data.today}
                  notify={notify}
                />
              )}
              {page === "knowledge" && (
                <KnowledgeBase
                  projects={data.projects}
                  today={data.today}
                  notify={notify}
                />
              )}
              {page === "review" && (
                <DailyReview data={data} changed={refresh} notify={notify} />
              )}
              {page === "dashboard" && range && (
                <Dashboard
                  data={data}
                  stats={stats}
                  range={range}
                  setRange={(next) => {
                    if (
                      (Date.parse(next.end) - Date.parse(next.start)) /
                        86400000 >
                      366
                    ) {
                      notify(uiText("一次最多查看 367 天，请缩小统计范围"), true);
                      return;
                    }
                    setRange(next);
                  }}
                  edit={setEditor}
                />
              )}
              {page === "settings" && (
                <SettingsPage data={data} changed={refresh} notify={notify} language={language} onLanguageChange={changeLanguage} />
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              DAYMARK <i /> PERSONAL PLANNING SYSTEM
            </span>
            <span>{uiText("让每一步，都有迹可循。")}</span>
          </footer>
        </div>
      </main>
      {editor && data && (
        <Editor
          key={`${editor.kind}-${editor.item?.id || "new"}`}
          editor={editor}
          data={data}
          close={() => setEditor(null)}
          saved={saved}
        />
      )}
      {rescheduleTask && data && (
        <RescheduleDialog
          task={rescheduleTask}
          today={data.today}
          close={() => setRescheduleTask(null)}
          save={async (date) => {
            await send(`/tasks/${rescheduleTask.id}/actions`, {
              action: "reschedule",
              date,
              version: rescheduleTask.version,
            });
            await saved(uiText("任务已重新安排"));
            setRescheduleTask(null);
          }}
        />
      )}
      {toast && (
        <div
          role={toast.error ? "alert" : "status"}
          className={`toast ${toast.error ? "error" : ""}`}
        >
          {toast.error ? <CircleHelp size={18} /> : <Check size={18} />}
          <span>{toast.message}</span>
          <button aria-label={uiText("关闭提示")} onClick={() => setToast(null)}>
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function RoutineCard({
  routine: r,
  data,
  edit,
}: {
  routine: Routine;
  data: Bootstrap;
  edit: () => void;
}) {
  const frequency =
    r.frequency === "daily"
      ? uiText("每天")
      : r.frequency === "every_n_days"
        ? uiFormat("每 {0} 天", r.interval)
        : r.frequency === "weekly"
          ? uiFormat("每 {0} 周", r.interval)
          : r.frequency === "weekdays"
            ? r.weekdays.map((d) => uiFormat("周{0}", "一二三四五六日"[d])).join("、")
            : uiFormat("每 {0} {1}", r.interval, r.interval_unit === "weeks" ? "周" : "天");
  const total = data.tasks.filter(
    (t) => t.routine_id === r.id && t.status !== "cancelled",
  );
  const complete = total.filter((t) => t.status === "completed").length;
  return (
    <section className="panel routine-card">
      <div className="routine-card-top">
        <div className="routine-icon">
          <Repeat2 size={21} />
        </div>
        <span className={`status-pill ${r.active ? "active" : "paused"}`}>
          {r.active ? uiText("已启用") : uiText("已暂停")}
        </span>
        <button className="text-button" onClick={edit}>
          {uiText("编辑")}
          <ArrowUpRight size={15} />
        </button>
      </div>
      <h2>{r.name}</h2>
      <p className="routine-description">
        {r.description || uiText("按自己的节奏，持续推进。")}
      </p>
      <div className="frequency-label">
        <Repeat2 size={14} />
        {frequency}
      </div>
      <div className="routine-meta">
        <span>
          <Clock3 size={14} />
          {r.preferred_time || uiText("时间待定")} · {r.estimated_duration} {uiText("分钟")}
        </span>
        <span>
          <CalendarDays size={14} />
          {r.start_date} {uiText("起")}{r.end_date ? uiFormat("，至 {0}", r.end_date) : ""}
        </span>
        {r.depends_on_routine_id && (
          <span>
            <ArrowRight size={14} />
            {uiText("依赖")} {r.offset_days} {uiText("天前的「")}
            {data.routines.find((x) => x.id === r.depends_on_routine_id)
              ?.name || uiText("重复任务")}
            」
          </span>
        )}
      </div>
      <div className="routine-foot">
        <span>
          <CheckCheck size={16} />
          {uiText("已完成")} <strong>{complete}</strong> {uiText("次")}
        </span>
        <span>{uiText("已生成")} {total.length} {uiText("项任务")}</span>
      </div>
    </section>
  );
}

function RescheduleDialog({
  task,
  today,
  close,
  save,
}: {
  task: Task;
  today: string;
  close: () => void;
  save: (date: string) => Promise<void>;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [date, setDate] = useState(today);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog ref={ref} className="editor-dialog small-dialog" onCancel={close}>
      <div className="dialog-head">
        <CalendarDays size={23} />
        <h2>{uiText("重新安排任务")}</h2>
        <button
          className="icon-button close-dialog"
          aria-label={uiText("关闭")}
          onClick={close}
        >
          <X size={18} />
        </button>
      </div>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await save(date);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="dialog-body">
          <p className="reschedule-title">{task.title}</p>
          <label className="field">
            <span>{uiText("新的计划日期")}</span>
            <input
              type="date"
              value={date}
              onInput={(e) => setDate(e.currentTarget.value)}
              onChange={(e) => setDate(e.target.value)}
              required
            />
          </label>
          <p className="form-hint">{uiText("原有开始时间、结束时间与历史记录会保留。")}</p>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
        </div>
        <div className="dialog-foot">
          <button type="button" className="button secondary" onClick={close}>
            {uiText("取消")}
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? uiText("保存中…") : uiText("确认改期")}
          </button>
        </div>
      </form>
    </dialog>
  );
}
