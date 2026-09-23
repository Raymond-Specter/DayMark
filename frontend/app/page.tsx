"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  ArrowDown,
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
  ProgressRing,
} from "@/components/Progress";
import { Dashboard, DailyReview, SettingsPage } from "@/components/Insights";
const Assistant = dynamic(() => import("@/components/assistant/Assistant"), {
  ssr: false,
});
const CalendarView = dynamic(() => import("@/components/CalendarView"), {
  ssr: false,
  loading: () => <div className="panel loading-panel">正在加载日历…</div>,
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
  english: string;
  subtitle: string;
  icon: typeof Sun;
}[] = [
  {
    id: "today",
    title: "今日概览",
    english: "Today",
    subtitle: "今日安排、下一项任务，以及整体推进到的阶段。",
    icon: Sun,
  },
  {
    id: "calendar",
    title: "我的日历",
    english: "Calendar",
    subtitle: "给重要的事情，安排一段专属的时间。",
    icon: CalendarDays,
  },
  {
    id: "tasks",
    title: "全部任务",
    english: "Tasks",
    subtitle: "每一个小的行动，都是向前的一步。",
    icon: ListTodo,
  },
  {
    id: "goals",
    title: "目标与项目",
    english: "Goals & Projects",
    subtitle: "从想去的地方，到脚下的每一步。",
    icon: Target,
  },
  {
    id: "routines",
    title: "重复任务",
    english: "Routines",
    subtitle: "让持续的投入，慢慢成为习惯。",
    icon: Repeat2,
  },
  {
    id: "learning",
    title: "学习档案",
    english: "Learning Archive",
    subtitle: "记录每天学了什么，把投入、进展与下一步串起来。",
    icon: BookOpenCheck,
  },
  {
    id: "knowledge",
    title: "知识库",
    english: "Knowledge Base",
    subtitle: "按日期和项目归档资料，让学习产出长期可找。",
    icon: LibraryBig,
  },
  {
    id: "review",
    title: "每日复盘",
    english: "Daily Review",
    subtitle: "回看今天，给明天留一点线索。",
    icon: Leaf,
  },
  {
    id: "dashboard",
    title: "数据统计",
    english: "Insights",
    subtitle: "看见投入，也看见一点一滴的成长。",
    icon: BarChart3,
  },
  {
    id: "assistant",
    title: "AI Assistant",
    english: "Local AI",
    subtitle: "用 DeepSeek 或本地 Qwen 理清想法，让下一步更清晰。",
    icon: Sparkles,
  },
  {
    id: "settings",
    title: "偏好设置",
    english: "Settings",
    subtitle: "让这个空间，适合你的节奏。",
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
              new Notification("Daymark · 任务提醒", {
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
          complete: "完成记录已保存，向前一步。",
          reopen: "任务已重新打开",
          reschedule: "任务已重新安排",
          cancel: "任务已取消",
          keep_overdue: "已保留逾期状态",
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

  return (
    <div className="app-shell">
      {mobileNav && (
        <button
          className="sidebar-overlay"
          aria-label="关闭导航"
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
            <strong>个人规划空间</strong>
            <span>Personal workspace</span>
          </div>
          <ChevronRight size={15} />
        </div>
        <span className="nav-caption">你的每一天</span>
        <nav aria-label="主要导航">
          {pages.slice(0, 3).map((p) => (
            <button
              key={p.id}
              onClick={() => navigate(p.id)}
              className={page === p.id ? "active" : ""}
            >
              <p.icon size={19} />
              <span>{p.title}</span>
              {p.id === "today" && remaining.length > 0 && (
                <i>{remaining.length}</i>
              )}
            </button>
          ))}
          {[
            { label: "规划", items: pages.slice(3, 5) },
            { label: "知识与回顾", items: pages.slice(5, 9) },
            { label: "智能工作台", items: pages.slice(9, 10) },
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
                  <span>{p.title}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <div className="little-sun">✳</div>
            <strong>按自己的节奏，向前。</strong>
            <p>A little progress, every day.</p>
          </div>
          <button
            className={`settings-nav ${page === "settings" ? "active" : ""}`}
            onClick={() => navigate("settings")}
          >
            <Settings size={18} />
            偏好设置
          </button>
          <div className="profile">
            <div className="profile-avatar">ME</div>
            <div>
              <strong>我的空间</strong>
              <span>
                <i />
                本地存储 · 私人规划
              </span>
            </div>
          </div>
        </div>
      </aside>
      <main className="main-workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="打开导航"
              onClick={() => setMobileNav(true)}
            >
              <Menu size={22} />
            </button>
            <span>工作空间</span>
            <ChevronRight size={13} />
            <strong>{currentPage.title}</strong>
          </div>
          <div className="topbar-actions">
            <span className="today-chip">
              <CalendarDays size={14} />
              {data?.today ? dateLabel(data.today) : "你的个人规划系统"}
            </span>
            <button
              className="icon-button"
              title="刷新数据"
              aria-label="刷新数据"
              disabled={loading}
              onClick={async () => {
                try {
                  await send("/scheduler/sync", {});
                  await refresh();
                  notify("数据已同步");
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
                aria-label={`提醒通知${unread ? `，${unread} 条未读` : ""}`}
                onClick={() => setNotificationOpen(!notificationOpen)}
              >
                <Bell size={19} />
                {unread > 0 && <i />}
              </button>
              {notificationOpen && (
                <section className="notification-popover">
                  <div>
                    <h3>提醒中心</h3>
                    <span>{unread} 条未读</span>
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
                          <p>
                            {deadlineLabel(n.due_at, data.settings.timezone)}
                          </p>
                        </div>
                      </button>
                    ))
                  ) : (
                    <div className="notification-empty">
                      <Bell size={25} />
                      <p>
                        还没有提醒
                        <br />
                        <small>可为任务或重复规则设置提醒。</small>
                      </p>
                    </div>
                  )}
                </section>
              )}
            </div>
            <div className="topbar-avatar">M</div>
          </div>
        </header>
        <div className={`page-content page-${page}`}>
          <div className="page-heading">
            <div>
              <div className="page-title-line">
                <h1>{currentPage.title}</h1>
                <span>{currentPage.english}</span>
                {page === "today" && <span className="today-dot" />}
              </div>
              <p>{currentPage.subtitle}</p>
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
                  ? "新建目标"
                  : page === "routines"
                    ? "新建重复任务"
                    : "新建任务"}
              </button>
            )}
          </div>
          {page === "assistant" ? (
            <Assistant changed={() => void refresh()} />
          ) : loading ? (
            <div className="panel loading-panel">
              <LoaderCircle className="spin" size={28} />
              <h2>正在准备你的规划空间</h2>
              <p>同步日历、任务与完成记录…</p>
            </div>
          ) : loadError || !data || !today || !stats ? (
            <div className="panel large-empty">
              <CircleHelp size={36} />
              <h2>暂时无法连接规划服务</h2>
              <p>{loadError || "请确认后端服务已启动。"}</p>
              <button className="button primary" onClick={initialize}>
                <RefreshCw size={16} />
                重新连接
              </button>
            </div>
          ) : (
            <>
              {page === "today" && (
                <>
                  <section className="today-hero">
                    <div className="hero-main">
                      <div className="hero-kicker">
                        <span className="hero-live-dot" /> DAILY BRIEFING
                        <span className="hero-date">{dateLabel(data.today)}</span>
                      </div>
                      <h2>
                        {remaining.length
                          ? `今天还有 ${remaining.length} 项待完成。`
                          : complete.length
                            ? "今天的计划已完成。"
                            : "今天，从一件事开始。"}
                      </h2>
                      <p>
                        {nextTask
                          ? `下一项：${nextTask.title}${nextTask.start_time ? ` · ${nextTask.start_time}` : " · 时间待定"}`
                          : remaining.length
                            ? "今天的任务正在等待前置任务，先检查依赖关系。"
                          : complete.length
                            ? "完成记录已保存。你可以写下今天的复盘。"
                            : "还没有今天的安排，添加一项任务即可开始。"}
                      </p>
                      <div className="hero-bottom">
                        <div className="hero-stat">
                          <small>COMPLETED</small>
                          <strong>{complete.length}<span> / {remaining.length + complete.length}</span></strong>
                          <span>已完成任务</span>
                        </div>
                        <div className="hero-stat">
                          <small>PLANNED</small>
                          <strong>{hours(plannedMinutes)}<span> h</span></strong>
                          <span>今日计划时长</span>
                        </div>
                        <div className="hero-stat">
                          <small>PROJECTS</small>
                          <strong>{activeProjects.length}</strong>
                          <span>进行中项目</span>
                        </div>
                      </div>
                    </div>
                    <div className="hero-progress">
                      <ProgressRing
                        value={dailyPercent}
                        size={125}
                        label="今日完成率"
                      />
                      <p>
                        {complete.length} / {remaining.length + complete.length}{" "}
                        TASKS
                      </p>
                      <button onClick={() => navigate("calendar")}>
                        查看日历 <ArrowUpRight size={14} />
                      </button>
                    </div>
                    <div className="hero-decoration" />
                  </section>
                  <section className="phase-strip">
                    <Flag size={18} />
                    <div className="phase-strip-label">
                      <strong>当前阶段</strong>
                      <span>整体规划</span>
                    </div>
                    <div className="phase-items">
                      {activeProjects.length ? (
                        activeProjects.slice(0, 3).map((p) => (
                          <button key={p.id} onClick={() => navigate("goals")}>
                            <i style={{ background: p.color }} />
                            <div>
                              <strong>{p.name}</strong>
                              <span>
                                {typeof p.current_milestone === "string"
                                  ? p.current_milestone
                                  : p.current_milestone?.name ||
                                    (p.total
                                      ? "已生成任务全部完成"
                                      : "待设置里程碑")}
                              </span>
                            </div>
                            <small>
                              {p.completed}/{p.total}
                            </small>
                          </button>
                        ))
                      ) : (
                        <span className="phase-empty">
                          添加项目和里程碑后，这里展示你正在推进的阶段。
                        </span>
                      )}
                    </div>
                    <button
                      className="text-button"
                      onClick={() => navigate("goals")}
                    >
                      查看全局
                      <ArrowUpRight size={14} />
                    </button>
                  </section>
                  <div className="today-layout">
                    <div className="today-main">
                      <section className="panel today-tasks-panel">
                        <div className="panel-heading">
                          <div className="heading-with-icon">
                            <div className="section-icon">
                              <ListTodo size={19} />
                            </div>
                            <h2>今天要做什么</h2>
                            <span className="count-pill">
                              {remaining.length}
                            </span>
                          </div>
                          <div className="sort-caption">
                            <ArrowDown size={12} />
                            时间 · 优先级
                          </div>
                        </div>
                        {remaining.length ? (
                          <div className="today-timeline">
                            {remaining.map((t, i) => (
                              <div className="timeline-entry" key={t.id}>
                                <div className="timeline-time">
                                  <strong>{t.start_time || "待定"}</strong>
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
                                ? "今天的任务都完成了"
                                : "今天还没有安排"}
                            </h3>
                            <p>
                              {complete.length
                                ? "去每日复盘中记录一下今天的投入和感受吧。"
                                : "添加一个任务，或创建会自动出现的重复任务。"}
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
                                ? "记录今天"
                                : "添加今天的第一件事"}
                            </button>
                          </div>
                        )}
                        <div className="completed-toggle">
                          <button
                            onClick={() => setShowCompleted(!showCompleted)}
                          >
                            <CheckCheck size={16} />
                            已完成任务<span>{complete.length}</span>
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
                                完成一件任务后，记录会出现在这里。
                              </p>
                            ))}
                        </div>
                      </section>
                      {today.unfinished_yesterday.length > 0 && (
                        <section className="panel yesterday-panel">
                          <div className="panel-heading">
                            <div>
                              <span className="eyebrow">
                                UNFINISHED YESTERDAY
                              </span>
                              <h2>
                                昨天未完成的事{" "}
                                <span className="count-pill">
                                  {today.unfinished_yesterday.length}
                                </span>
                              </h2>
                            </div>
                            <Clock3 size={18} />
                          </div>
                          <p className="panel-description">
                            留在记录里，由你决定下一步。
                          </p>
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
                            <h2>更早的待处理事项</h2>
                            <span className="status-pill overdue">
                              需要你的决定
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
                            NEXT UP
                          </span>
                          <Flag size={15} />
                        </div>
                        <h3>
                          {nextTask ? "从这一件开始" : "为今天留一点方向"}
                        </h3>
                        {nextTask ? (
                          <>
                            <h2>{nextTask.title}</h2>
                            <p>
                              {nextTask.start_time || "时间待定"} <span>·</span>{" "}
                              {nextTask.estimated_duration} 分钟
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
                              查看任务
                              <ArrowRight size={16} />
                            </button>
                          </>
                        ) : (
                          <>
                            <p>
                              {remaining.length
                                ? "当前任务正在等待前置任务完成。可先检查依赖关系。"
                                : "从一个小而具体的行动开始，慢慢建立你的节奏。"}
                            </p>
                            <button onClick={() => setEditor({ kind: "task" })}>
                              添加一个行动
                              <Plus size={16} />
                            </button>
                          </>
                        )}
                      </section>
                      <section className="panel day-map">
                        <div className="panel-heading">
                          <div>
                            <span className="eyebrow">TIME BLOCKS</span>
                            <h2>今日时间表</h2>
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
                                  <small>{t.end_time || `${t.estimated_duration} 分钟`}</small>
                                </span>
                              </button>
                            ))}
                            {timedTasks.length > 4 && (
                              <span className="day-map-more">
                                还有 {timedTasks.length - 4} 项 · 在日历中查看
                              </span>
                            )}
                          </div>
                        ) : (
                          <p className="day-map-empty">今天没有设定具体时间的任务。</p>
                        )}
                        <button
                          className="day-map-link"
                          onClick={() => navigate("calendar")}
                        >
                          查看完整日历 <ArrowUpRight size={14} />
                        </button>
                      </section>
                      <section className="panel deadlines-panel">
                        <div className="panel-heading">
                          <h2>即将到期</h2>
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
                            <p>暂时没有临近的截止事项</p>
                            <span>留一点余裕，从容向前。</span>
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
                            给今天一个小小的回望<strong>写每日复盘</strong>
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
                        aria-label="搜索任务"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="搜索任务名称或备注…"
                      />
                    </label>
                    <label>
                      <span className="sr-only">任务状态</span>
                      <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                      >
                        <option value="all">全部状态</option>
                        <option value="open">未完成</option>
                        <option value="pending">待完成</option>
                        <option value="completed">已完成</option>
                        <option value="overdue">已逾期</option>
                        <option value="rescheduled">已改期</option>
                        <option value="cancelled">已取消</option>
                      </select>
                    </label>
                    <label>
                      <span className="sr-only">所属项目筛选</span>
                      <select
                        value={projectFilter}
                        onChange={(e) => setProjectFilter(e.target.value)}
                      >
                        <option value="all">全部项目</option>
                        <option value="none">独立任务</option>
                        {data.projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span className="sr-only">计划日期筛选</span>
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
                        清除
                      </button>
                    )}
                  </div>
                  <section className="panel all-tasks-panel">
                    <div className="panel-heading">
                      <h2>
                        任务清单{" "}
                        <span className="count-pill">
                          {filteredTasks.length}
                        </span>
                      </h2>
                      <span className="sort-caption">日期 / 时间 / 优先级</span>
                    </div>
                    {filteredTasks.length ? (
                      filteredTasks.map((t) => row(t, { showDate: true }))
                    ) : (
                      <div className="large-empty">
                        <ListTodo size={35} />
                        <h2>
                          {data.tasks.length
                            ? "没有匹配的任务"
                            : "从一件小事开始"}
                        </h2>
                        <p>
                          {data.tasks.length
                            ? "试试调整搜索词或筛选条件。"
                            : "把想做的事情放进这里，再慢慢安排时间。"}
                        </p>
                        {!data.tasks.length && (
                          <button
                            className="button primary"
                            onClick={() => setEditor({ kind: "task" })}
                          >
                            <Plus size={16} />
                            创建任务
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
                      设定一次规则，让任务按节奏出现。所有任务仍可单独调整，完成记录会一直保留。
                    </p>
                    <span>
                      {data.routines.filter((r) => r.active).length} 条启用中
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
                      <p className="eyebrow">SMALL STEPS, REPEATED</p>
                      <h2>给坚持，一个自动开始的方式</h2>
                      <p>
                        每天、每周，或你自己的节奏。
                        <br />
                        创建重复规则，系统会自动生成对应的任务。
                      </p>
                      <button
                        className="button primary"
                        onClick={() => setEditor({ kind: "routine" })}
                      >
                        <Plus size={16} />
                        创建重复任务
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
                      notify("一次最多查看 367 天，请缩小统计范围", true);
                      return;
                    }
                    setRange(next);
                  }}
                  edit={setEditor}
                />
              )}
              {page === "settings" && (
                <SettingsPage data={data} changed={refresh} notify={notify} />
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              DAYMARK <i /> PERSONAL PLANNING SYSTEM
            </span>
            <span>让每一步，都有迹可循。</span>
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
            await saved("任务已重新安排");
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
          <button aria-label="关闭提示" onClick={() => setToast(null)}>
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
      ? "每天"
      : r.frequency === "every_n_days"
        ? `每 ${r.interval} 天`
        : r.frequency === "weekly"
          ? `每 ${r.interval} 周`
          : r.frequency === "weekdays"
            ? r.weekdays.map((d) => `周${"一二三四五六日"[d]}`).join("、")
            : `每 ${r.interval} ${r.interval_unit === "weeks" ? "周" : "天"}`;
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
          {r.active ? "已启用" : "已暂停"}
        </span>
        <button className="text-button" onClick={edit}>
          编辑
          <ArrowUpRight size={15} />
        </button>
      </div>
      <h2>{r.name}</h2>
      <p className="routine-description">
        {r.description || "按自己的节奏，持续推进。"}
      </p>
      <div className="frequency-label">
        <Repeat2 size={14} />
        {frequency}
      </div>
      <div className="routine-meta">
        <span>
          <Clock3 size={14} />
          {r.preferred_time || "时间待定"} · {r.estimated_duration} 分钟
        </span>
        <span>
          <CalendarDays size={14} />
          {r.start_date} 起{r.end_date ? `，至 ${r.end_date}` : ""}
        </span>
        {r.depends_on_routine_id && (
          <span>
            <ArrowRight size={14} />
            依赖 {r.offset_days} 天前的「
            {data.routines.find((x) => x.id === r.depends_on_routine_id)
              ?.name || "重复任务"}
            」
          </span>
        )}
      </div>
      <div className="routine-foot">
        <span>
          <CheckCheck size={16} />
          已完成 <strong>{complete}</strong> 次
        </span>
        <span>已生成 {total.length} 项任务</span>
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
        <h2>重新安排任务</h2>
        <button
          className="icon-button close-dialog"
          aria-label="关闭"
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
            <span>新的计划日期</span>
            <input
              type="date"
              value={date}
              onInput={(e) => setDate(e.currentTarget.value)}
              onChange={(e) => setDate(e.target.value)}
              required
            />
          </label>
          <p className="form-hint">原有开始时间、结束时间与历史记录会保留。</p>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
        </div>
        <div className="dialog-foot">
          <button type="button" className="button secondary" onClick={close}>
            取消
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "保存中…" : "确认改期"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
