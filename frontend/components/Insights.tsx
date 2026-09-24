"use client";
import { uiText, uiFormat, type Language } from "@/lib/i18n";
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Bell,
  Check,
  CheckCheck,
  Clock3,
  Download,
  ExternalLink,
  FolderOpen,
  Leaf,
  Plug,
  Save,
  ShieldCheck,
} from "lucide-react";
import { api, dateLabel, deadlineLabel, hours, send } from "@/lib/api";
import type { Bootstrap, EditorState, Review, Statistics } from "@/lib/types";
import { ProgressBar } from "./Progress";

export function Dashboard({
  stats,
  data,
  setRange,
  range,
  edit,
}: {
  stats: Statistics;
  data: Bootstrap;
  setRange: (value: { start: string; end: string }) => void;
  range: { start: string; end: string };
  edit: (e: EditorState) => void;
}) {
  const maxMinutes = Math.max(
    60,
    ...stats.daily.flatMap((d) => [d.planned_minutes, d.actual_minutes]),
  );
  return (
    <>
      <div className="section-toolbar">
        <span className="subtle-note">
          <BarChart3 size={16} />
          {uiText("用真实记录，看看走过的路")}
        </span>
        <div className="date-range">
          <label>
            <span className="sr-only">{uiText("统计开始日期")}</span>
            <input
              type="date"
              value={range.start}
              onInput={(e) => e.currentTarget.value && setRange({ ...range, start: e.currentTarget.value })}
              max={range.end}
              onChange={(e) =>
                e.target.value && setRange({ ...range, start: e.target.value })
              }
            />
          </label>
          <span>—</span>
          <label>
            <span className="sr-only">{uiText("统计结束日期")}</span>
            <input
              type="date"
              value={range.end}
              onInput={(e) => e.currentTarget.value && setRange({ ...range, end: e.currentTarget.value })}
              min={range.start}
              onChange={(e) =>
                e.target.value && setRange({ ...range, end: e.target.value })
              }
            />
          </label>
        </div>
      </div>
      <div className="metric-grid dashboard-metrics">
        {[
          {
            label: uiText("今日完成"),
            value: stats.completed_today,
            unit: uiText("项"),
            icon: CheckCheck,
            note: uiText("以实际完成日期统计"),
          },
          {
            label: uiText("本周完成"),
            value: stats.completed_week,
            unit: uiText("项"),
            icon: Activity,
            note: uiText("本周一至今"),
          },
          {
            label: uiText("区间完成率"),
            value: Math.round(stats.completion_rate),
            unit: "%",
            icon: BarChart3,
            note: uiFormat("{0} / {1} 项任务", stats.completed_tasks, stats.total_tasks),
          },
          {
            label: uiText("计划 / 实际"),
            value: `${hours(stats.planned_minutes)} / ${hours(stats.actual_minutes)}`,
            unit: "h",
            icon: Clock3,
            note: uiText("实际时间来自每日复盘"),
          },
        ].map((m) => (
          <div className="panel metric-card" key={m.label}>
            <div className="metric-top">
              <span>{m.label}</span>
              <m.icon size={17} />
            </div>
            <div className="metric-value">
              {m.value}
              <small>{m.unit}</small>
            </div>
            <p>{m.note}</p>
          </div>
        ))}
      </div>
      <div className="insights-grid">
        <section className="panel chart-panel">
          <div className="panel-heading">
            <div>
              <h2>{uiText("计划与实际投入")}</h2>
            </div>
            <div className="chart-legend">
              <span>
                <i className="blue" />
                {uiText("计划")}
              </span>
              <span>
                <i className="mint" />
                {uiText("实际")}
              </span>
            </div>
          </div>
          <div className="bar-chart" aria-label={uiText("每日计划与实际时间柱状图")}>
            {stats.daily.length ? (
              stats.daily.map((day) => (
                <div
                  className="chart-column"
                  key={day.date}
                  title={uiFormat("{0}：计划 {1} 分钟，实际 {2} 分钟", day.date, day.planned_minutes, day.actual_minutes)}
                >
                  <div className="bar-pair">
                    <div
                      style={{
                        height: `${(day.planned_minutes / maxMinutes) * 100}%`,
                      }}
                    />
                    <div
                      style={{
                        height: `${(day.actual_minutes / maxMinutes) * 100}%`,
                      }}
                    />
                  </div>
                  <span>{day.date.slice(5).replace("-", "/")}</span>
                </div>
              ))
            ) : (
              <div className="chart-empty">{uiText("所选时间范围暂无记录")}</div>
            )}
          </div>
          <div className="chart-baseline">
            <span>0 h</span>
            <span>{uiText("纵轴最大值")} {hours(maxMinutes)} h</span>
          </div>
        </section>
        <section className="panel distribution-panel">
          <div className="panel-heading">
            <div>
              <h2>{uiText("项目时间分布")}</h2>
            </div>
            <FolderOpen size={19} />
          </div>
          {stats.project_distribution.length ? (
            stats.project_distribution.map((p) => (
              <div
                className="distribution-row"
                key={p.project_id || "unassigned"}
              >
                <div>
                  <span>
                    <i style={{ backgroundColor: p.color || "#acbcf7" }} />
                    {p.name}
                  </span>
                  <strong>
                    {hours(p.actual_minutes)} h <small>{uiText("实际")}</small>
                  </strong>
                </div>
                <ProgressBar
                  value={
                    stats.actual_minutes
                      ? (p.actual_minutes / stats.actual_minutes) * 100
                      : 0
                  }
                  color={p.color}
                />
                <p>{uiText("计划")} {hours(p.planned_minutes)} h</p>
              </div>
            ))
          ) : (
            <div className="empty-inline">
              <FolderOpen size={27} />
              <p>
                {uiText("在每日复盘中记录项目投入，")}
                <br />
                {uiText("了解时间如何分配。")}
              </p>
            </div>
          )}
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>{uiText("即将到期")}</h2>
          </div>
        </div>
        {stats.upcoming_deadlines.length ? (
          <div className="deadline-grid">
            {stats.upcoming_deadlines.map((t) => (
              <button
                key={t.id}
                className="deadline-card"
                onClick={() => edit({ kind: "task", item: t })}
              >
                <span className={`priority-dot p${t.priority}`} />
                <div>
                  <strong>{t.title}</strong>
                  <p>{deadlineLabel(t.deadline!, data.settings.timezone)}</p>
                </div>
                <ArrowUpRight size={17} />
              </button>
            ))}
          </div>
        ) : (
          <p className="empty-line">{uiText("当前没有临近的截止事项。")}</p>
        )}
      </section>
    </>
  );
}

export function DailyReview({
  data,
  changed,
  notify,
}: {
  data: Bootstrap;
  changed: () => Promise<void>;
  notify: (text: string, error?: boolean) => void;
}) {
  const [date, setDate] = useState(data.today);
  const [review, setReview] = useState<Review | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setReview(null);
    setError("");
    api<Review>(`/reviews/${date}`)
      .then((r) => {
        if (active) setReview(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [date]);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!review) return;
    setBusy(true);
    setError("");
    try {
      const result = await send<Review>(
        `/reviews/${date}`,
        {
          actual_minutes: review.actual_minutes,
          energy_level: review.energy_level,
          notes: review.notes,
          project_minutes: review.project_minutes,
        },
        "PUT",
      );
      setReview(result);
      await changed();
      notify(uiText("今日复盘已保存"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const energy = [uiText("有点疲惫"), uiText("状态偏低"), uiText("平稳"), uiText("状态不错"), uiText("精力充沛")];
  return (
    <>
      <div className="section-toolbar">
        <span className="subtle-note">
          <Leaf size={16} />
          {uiText("留一点时间，听听今天的自己")}
        </span>
        <label className="date-range">
          <span className="sr-only">{uiText("复盘日期")}</span>
          <input
            type="date"
            max={data.today}
            value={date}
            onInput={(e) => e.currentTarget.value && setDate(e.currentTarget.value)}
            onChange={(e) => e.target.value && setDate(e.target.value)}
          />
        </label>
      </div>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      {!review ? (
        <div className="panel loading-panel">
          {error ? uiText("复盘加载失败，请重新选择日期重试。") : uiText("正在读取当天记录…")}
        </div>
      ) : (
        <div className="review-grid">
          <form className="panel review-form" onSubmit={save}>
            <div className="panel-heading">
              <div>
                <h2>{dateLabel(date)}{uiText("的复盘")}</h2>
              </div>
              <span
                className={`status-pill ${review.saved ? "completed" : "pending"}`}
              >
                {review.saved ? uiText("已记录") : uiText("未保存")}
              </span>
            </div>
            <label className="field">
              <span>{uiText("实际学习 / 工作时间")}</span>
              <div className="minutes-input">
                <input
                  type="number"
                  min={0}
                  max={1440}
                  required
                  value={review.actual_minutes}
                  onChange={(e) =>
                    setReview({
                      ...review,
                      actual_minutes: Number(e.target.value),
                    })
                  }
                />
                <span>{uiText("分钟")}</span>
                <small>{hours(review.actual_minutes)} {uiText("小时")}</small>
              </div>
            </label>
            <fieldset className="energy-field">
              <legend>{uiText("今天的精力状态")}</legend>
              <div>
                {energy.map((label, i) => (
                  <button
                    key={label}
                    type="button"
                    className={review.energy_level === i + 1 ? "active" : ""}
                    onClick={() =>
                      setReview({ ...review, energy_level: i + 1 })
                    }
                    aria-pressed={review.energy_level === i + 1}
                  >
                    <span>{["◡", "◔", "◑", "◕", "●"][i]}</span>
                    <small>{label}</small>
                  </button>
                ))}
              </div>
            </fieldset>
            <label className="field">
              <span>{uiText("今天的记录")}</span>
              <textarea
                rows={6}
                value={review.notes}
                maxLength={20000}
                onChange={(e) =>
                  setReview({ ...review, notes: e.target.value })
                }
                placeholder={uiText("今天推进了什么？哪里有些卡住？也可以只是写下一点感受。")}
              />
            </label>
            {data.projects.length > 0 && (
              <div className="review-allocation">
                <h3>
                  {uiText("项目投入")} <span>{uiText("可选 · 单位为分钟")}</span>
                </h3>
                {data.projects.map((p) => (
                  <label key={p.id}>
                    <span>{p.name}</span>
                    <input
                      type="number"
                      min={0}
                      max={1440}
                      value={review.project_minutes[p.id] || 0}
                      onChange={(e) =>
                        setReview({
                          ...review,
                          project_minutes: {
                            ...review.project_minutes,
                            [p.id]: Number(e.target.value),
                          },
                        })
                      }
                    />
                  </label>
                ))}
                <p className="form-hint">
                  {uiText("已分配")}{" "}
                  {Object.values(review.project_minutes).reduce(
                    (a, b) => a + b,
                    0,
                  )}{" "}
                  / {review.actual_minutes}{" "}
                  {uiText("分钟。未分配的时间保留在当天总投入中。")}
                </p>
              </div>
            )}
            <div className="review-footer">
              <span>{uiText("保存时记录当天任务状态快照")}</span>
              <button className="button primary" disabled={busy}>
                <Save size={16} />
                {busy ? uiText("保存中…") : uiText("保存复盘")}
              </button>
            </div>
          </form>
          <div className="review-aside">
            <section className="panel">
              <div className="panel-heading">
                <h2>
                  <CheckCheck size={18} />
                  {uiText("完成的事情")}
                </h2>
                <span className="count-pill">
                  {review.completed_tasks.length}
                </span>
              </div>
              {review.completed_tasks.length ? (
                <ul className="snapshot-list">
                  {review.completed_tasks.map((t) => (
                    <li key={t.id}>
                      <Check size={15} />
                      {t.title}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty-line">{uiText("当天还没有完成的任务记录。")}</p>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <h2>
                  <Clock3 size={18} />
                  {uiText("还在路上的事情")}
                </h2>
                <span className="count-pill">
                  {review.unfinished_tasks.length}
                </span>
              </div>
              {review.unfinished_tasks.length ? (
                <ul className="snapshot-list unfinished">
                  {review.unfinished_tasks.map((t) => (
                    <li key={t.id}>
                      <i />
                      {t.title}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty-line">{uiText("没有未完成事项。")}</p>
              )}
            </section>
            <div className="review-note">
              <Leaf size={22} />
              <p>
                {uiText("记录进展，也留住真实的感受。")}
                <br />
                {uiText("不必每天都完美。")}
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function SettingsPage({
  data,
  changed,
  notify,
  language,
  onLanguageChange,
}: {
  data: Bootstrap;
  changed: () => Promise<void>;
  notify: (text: string, error?: boolean) => void;
  language: Language;
  onLanguageChange: (next: Language) => void;
}) {
  const [timezone, setTimezone] = useState(data.settings.timezone);
  const [dayStart, setDayStart] = useState(data.settings.day_start);
  const [permission, setPermission] = useState("default");
  const [busy, setBusy] = useState(false);
  useEffect(
    () =>
      setPermission(
        "Notification" in window ? Notification.permission : "unsupported",
      ),
    [],
  );
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await send("/settings", { timezone, day_start: dayStart }, "PUT");
      await changed();
      notify(uiText("偏好设置已保存"));
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function requestNotifications() {
    if (!("Notification" in window)) return;
    setPermission(await Notification.requestPermission());
  }
  async function download() {
    try {
      const backup = await api("/export");
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(backup, null, 2)], {
          type: "application/json",
        }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `daymark-backup-${data.today}.json`;
      link.click();
      URL.revokeObjectURL(url);
      notify(uiText("数据备份已导出"));
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  return (
    <div className="settings-layout">
      <form className="panel settings-card" onSubmit={save}>
        <div className="panel-heading">
          <div>
            <h2>{uiText("时间与偏好")}</h2>
          </div>
          <Clock3 size={20} />
        </div>
        <div className="form-grid">
          <label className="field">
            <span>{uiText("界面语言")}</span>
            <select
              value={language}
              onChange={(event) => onLanguageChange(event.target.value as Language)}
            >
              <option value="en">English</option>
              <option value="zh">中文</option>
            </select>
          </label>
          <label className="field">
            <span>{uiText("时区")}</span>
            <input
              value={timezone}
              required
              list="timezones"
              onChange={(e) => setTimezone(e.target.value)}
            />
            <datalist id="timezones">
              <option value="Asia/Shanghai" />
              <option value="Asia/Hong_Kong" />
              <option value="America/New_York" />
              <option value="America/Los_Angeles" />
              <option value="Europe/London" />
              <option value="UTC" />
            </datalist>
          </label>
          <label className="field">
            <span>{uiText("默认每日开始时间")}</span>
            <input
              type="time"
              value={dayStart}
              onInput={(e) => setDayStart(e.currentTarget.value)}
              required
              onChange={(e) => setDayStart(e.target.value)}
            />
          </label>
        </div>
        <p className="form-hint">
          {uiText("日历与任务时间按此时区记录。未设置具体时间的任务，默认以每日开始时间作为提醒基准。")}
        </p>
        <button className="button primary" disabled={busy}>
          <Save size={16} />
          {busy ? uiText("保存中…") : uiText("保存设置")}
        </button>
      </form>
      <section className="panel settings-card">
        <div className="panel-heading">
          <div>
            <h2>{uiText("通知与提醒")}</h2>
          </div>
          <Bell size={20} />
        </div>
        <div className="settings-feature">
          <div>
            <h3>{uiText("浏览器系统通知")}</h3>
            <p>
              {permission === "granted"
                ? uiText("已允许通知，页面打开时接收任务提醒。")
                : permission === "denied"
                  ? uiText("通知已被浏览器阻止，可在地址栏的站点设置中重新开启。")
                  : permission === "unsupported"
                    ? uiText("当前浏览器不支持系统通知，仍可使用应用内提醒。")
                    : uiText("允许后，页面打开时可收到系统通知。")}
            </p>
          </div>
          <button
            className="button secondary small"
            onClick={requestNotifications}
            disabled={permission !== "default"}
          >
            {permission === "granted"
              ? uiText("已开启")
              : permission === "denied"
                ? uiText("已阻止")
                : permission === "unsupported"
                  ? uiText("不支持")
                  : uiText("开启通知")}
          </button>
        </div>
        <div className="info-box">
          <ShieldCheck size={18} />
          <p>
            {uiText("当前版本在应用打开时检查提醒；关闭网页或系统休眠后，无法保证系统通知准时送达。待触发的提醒会保留，并在下次打开时检查。Google Calendar 接口已预留。")}
          </p>
        </div>
      </section>
      <section className="panel settings-card">
        <div className="panel-heading">
          <div>
            <h2>{uiText("数据备份")}</h2>
          </div>
          <Download size={20} />
        </div>
        <div className="settings-feature">
          <div>
            <h3>{uiText("导出完整数据")}</h3>
            <p>
              {uiText("将目标、项目、任务、完成记录与每日复盘导出为 JSON 文件。数据保存在本机 SQLite 数据库中。")}
            </p>
          </div>
          <button
            type="button"
            className="button secondary small"
            onClick={download}
          >
            <Download size={15} />
            {uiText("导出备份")}
          </button>
        </div>
      </section>
      <section className="panel settings-card">
        <div className="panel-heading">
          <div>
            <h2>{uiText("未来扩展")}</h2>
          </div>
          <Plug size={20} />
        </div>
        <div className="integration-list">
          <div>
            <div className="integration-logo">G</div>
            <div>
              <h3>Google Calendar</h3>
              <p>{uiText("日历同步与可靠提醒")}</p>
            </div>
            <span className="status-pill">{uiText("接口已预留")}</span>
          </div>
          <div>
            <div className="integration-logo">
              <ExternalLink size={20} />
            </div>
            <div>
              <h3>AI Planner / OpenAI</h3>
              <p>{uiText("由你决定何时引入智能规划")}</p>
            </div>
            <span className="status-pill">{uiText("尚未启用")}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
