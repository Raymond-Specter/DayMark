"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, Clock3, FileText, Plus, Sparkles } from "lucide-react";
import { api, dateLabel, send } from "@/lib/api";
import type { LearningEntry, Project } from "@/lib/types";
import "./learning.css";

const types = [
  ["study", "学习"], ["assignment", "作业"], ["project", "项目"],
  ["output", "产出"], ["reading", "阅读"], ["research", "研究"],
  ["internship", "实习"], ["exam", "考试"], ["reflection", "反思"], ["other", "其他"],
] as const;

export default function LearningArchive({ projects, today, notify }: {
  projects: Project[]; today: string; notify: (message: string, error?: boolean) => void;
}) {
  const [entries, setEntries] = useState<LearningEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [project, setProject] = useState("all");
  const [entryType, setEntryType] = useState("all");
  const [formOpen, setFormOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ date: today, project_id: "", title: "", entry_type: "study",
    duration_minutes: 60, progress: 100, reflection: "", problems: "", next_action: "" });
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (project !== "all") params.set("project_id", project);
      if (entryType !== "all") params.set("entry_type", entryType);
      setEntries(await api<LearningEntry[]>(`/learning-entries?${params}`));
    } catch (error) { notify((error as Error).message, true); }
    finally { setLoading(false); }
  }, [project, entryType, notify]);
  useEffect(() => { void load(); }, [load]);
  const totals = useMemo(() => ({
    minutes: entries.reduce((sum, row) => sum + row.duration_minutes, 0),
    documents: entries.reduce((sum, row) => sum + row.documents.length, 0),
    outputs: entries.filter((row) => row.entry_type === "output").length,
  }), [entries]);
  const grouped = useMemo(() => Object.entries(entries.reduce<Record<string, LearningEntry[]>>((result, row) => {
    (result[row.date] ||= []).push(row); return result;
  }, {})), [entries]);
  async function createEntry(event: React.FormEvent) {
    event.preventDefault(); setBusy(true);
    try {
      await send("/learning-entries", { ...form, project_id: form.project_id || null,
        status: form.progress === 100 ? "completed" : "partial" });
      setForm({ ...form, title: "", reflection: "", problems: "", next_action: "" });
      setFormOpen(false); notify("学习记录已保存"); await load();
    } catch (error) { notify((error as Error).message, true); }
    finally { setBusy(false); }
  }
  return <div className="learning-page">
    <div className="learning-stats">
      <article><Clock3 /><span>实际投入<strong>{Math.floor(totals.minutes / 60)}h {totals.minutes % 60}m</strong></span></article>
      <article><BookOpen /><span>学习记录<strong>{entries.length}</strong></span></article>
      <article><FileText /><span>关联资料<strong>{totals.documents}</strong></span></article>
      <article><Sparkles /><span>产出记录<strong>{totals.outputs}</strong></span></article>
    </div>
    <section className="learning-toolbar panel">
      <div><select aria-label="学习项目筛选" value={project} onChange={(e) => setProject(e.target.value)}>
        <option value="all">全部项目</option>{projects.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select><select aria-label="学习类型筛选" value={entryType} onChange={(e) => setEntryType(e.target.value)}>
        <option value="all">全部类型</option>{types.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></div>
      <button className="button primary" onClick={() => setFormOpen(!formOpen)}><Plus size={17} />记录实际学习</button>
    </section>
    {formOpen && <form className="learning-form panel" onSubmit={createEntry}>
      <div className="panel-heading"><h2>今天实际做了什么？</h2><span>Task 之外也可以独立记录</span></div>
      <div className="learning-form-grid">
        <label>日期<input required type="date" value={form.date} onChange={(e) => setForm({...form,date:e.target.value})} /></label>
        <label>项目<select value={form.project_id} onChange={(e) => setForm({...form,project_id:e.target.value})}><option value="">暂不归类</option>{projects.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>类型<select value={form.entry_type} onChange={(e) => setForm({...form,entry_type:e.target.value})}>{types.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>实际时间（分钟）<input required min="0" max="10080" type="number" value={form.duration_minutes} onChange={(e) => setForm({...form,duration_minutes:Number(e.target.value)})} /></label>
        <label className="wide">标题<input required maxLength={200} value={form.title} onChange={(e) => setForm({...form,title:e.target.value})} placeholder="例如 Lecture 4 - Attention" /></label>
        <label className="wide">收获<textarea value={form.reflection} onChange={(e) => setForm({...form,reflection:e.target.value})} placeholder="我理解了什么？" /></label>
        <label>仍有问题<textarea value={form.problems} onChange={(e) => setForm({...form,problems:e.target.value})} /></label>
        <label>下一步<textarea value={form.next_action} onChange={(e) => setForm({...form,next_action:e.target.value})} /></label>
      </div><div className="form-actions"><button type="button" className="button secondary" onClick={() => setFormOpen(false)}>取消</button><button className="button primary" disabled={busy}>{busy ? "保存中…" : "保存记录"}</button></div>
    </form>}
    <section className="learning-timeline">
      {loading ? <div className="panel learning-empty">正在读取学习档案…</div> : grouped.length ? grouped.map(([day, rows]) => <div className="timeline-day" key={day}>
        <div className="timeline-date"><strong>{dateLabel(day, true)}</strong><span>{rows.reduce((sum,row)=>sum+row.duration_minutes,0)} min</span></div>
        <div className="timeline-items">{rows.map((row) => <article className="learning-card panel" key={row.id}>
          <div><span className="learning-type">{types.find(([value])=>value===row.entry_type)?.[1] || row.entry_type}</span><span>{projects.find((p)=>p.id===row.project_id)?.name || "未归类"}</span></div>
          <h2>{row.title}</h2><p>{row.reflection || row.description || "尚未填写学习收获。"}</p>
          {row.problems && <aside><strong>仍有问题</strong>{row.problems}</aside>}
          <footer><span><Clock3 size={14}/>{row.duration_minutes} min</span><span>{row.progress ?? "—"}%</span><span>{row.documents.length} 份资料</span></footer>
        </article>)}</div>
      </div>) : <div className="panel learning-empty"><BookOpen size={34}/><h2>还没有学习记录</h2><p>记录实际投入、收获和仍待解决的问题。</p></div>}
    </section>
  </div>;
}
