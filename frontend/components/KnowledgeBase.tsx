"use client";
import { uiText, uiFormat } from "@/lib/i18n";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, FileCode2, FileText, FolderOpen, LoaderCircle, Search, Upload } from "lucide-react";
import { api, dateLabel } from "@/lib/api";
import type { KnowledgeDocument, Project } from "@/lib/types";
import "./learning.css";

const documentTypes = [["note","笔记"],["slides","课件"],["assignment","作业"],["solution","解答"],["code","代码"],["paper","论文"],["output","产出"],["reflection","反思"],["reference","参考"],["exam","考试"],["other","其他"]] as const;

export default function KnowledgeBase({ projects, today, notify }: { projects: Project[]; today: string; notify: (message: string, error?: boolean) => void }) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [project, setProject] = useState("all"); const [type, setType] = useState("all");
  const [query, setQuery] = useState(""); const [uploadOpen, setUploadOpen] = useState(false);
  const [busy, setBusy] = useState(false); const fileInput = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState({ knowledge_date: today, project_id: "", document_type: "note", title: "", is_output: false, description: "" });
  const load = useCallback(async () => {
    try { const params = new URLSearchParams(); if(project!=="all")params.set("project_id",project); if(type!=="all")params.set("document_type",type); setDocuments(await api<KnowledgeDocument[]>(`/documents?${params}`)); }
    catch(error){notify((error as Error).message,true);}
  },[project,type,notify]);
  useEffect(()=>{void load();},[load]);
  const shown = documents.filter((row)=>`${row.title} ${row.original_filename || ""} ${row.description}`.toLowerCase().includes(query.toLowerCase()));
  async function upload(event: React.FormEvent){ event.preventDefault(); const file=fileInput.current?.files?.[0]; if(!file){notify(uiText("请选择文件"),true);return;} setBusy(true);
    try{const params=new URLSearchParams({...form,is_output:String(form.is_output),filename:file.name}); if(!form.project_id)params.delete("project_id");
      const response=await fetch(`/api/documents/upload?${params}`,{method:"POST",headers:{"Content-Type":file.type||"application/octet-stream"},body:file});
      if(!response.ok){const body=await response.json().catch(()=>({})); const detail=body.detail; throw new Error(typeof detail==="string"?detail:detail?.message||uiFormat("上传失败（{0}）", response.status));}
      notify(uiText("文档已保存到知识库")); setUploadOpen(false); if(fileInput.current)fileInput.current.value=""; setForm({...form,title:"",description:""}); await load();
    }catch(error){notify((error as Error).message,true);}finally{setBusy(false);}}
  return <div className="learning-page">
    <section className="knowledge-hero panel"><div><span>PERSONAL FILE CENTER</span><h2>{uiText("资料留在本机，按学习日期归档。")}</h2><p>{uiText("上传只进行本地保存与解析，不会自动发送到 DeepSeek。")}</p></div><button className="button primary" onClick={()=>setUploadOpen(!uploadOpen)}><Upload size={17}/>{uiText("上传资料")}</button></section>
    {uploadOpen&&<form className="learning-form panel" onSubmit={upload}><div className="panel-heading"><h2>{uiText("上传知识文档")}</h2><span>{uiText("文件 + 日期 + Project 即可")}</span></div><div className="learning-form-grid">
      <label className="wide upload-drop">{uiText("文件")}<input ref={fileInput} required type="file" accept=".txt,.md,.markdown,.csv,.json,.js,.ts,.py,.c,.cpp,.java,.sql,.yaml,.yml,.xml,.log,.ipynb,.pdf,.docx"/></label>
      <label>{uiText("知识日期")}<input required type="date" value={form.knowledge_date} onChange={(e)=>setForm({...form,knowledge_date:e.target.value})}/></label>
      <label>{uiText("项目")}<select value={form.project_id} onChange={(e)=>setForm({...form,project_id:e.target.value})}><option value="">{uiText("暂不归类")}</option>{projects.map((row)=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      <label>{uiText("文档类型")}<select value={form.document_type} onChange={(e)=>setForm({...form,document_type:e.target.value})}>{documentTypes.map(([value,label])=><option key={value} value={value}>{uiText(label)}</option>)}</select></label>
      <label className="check-label"><input type="checkbox" checked={form.is_output} onChange={(e)=>setForm({...form,is_output:e.target.checked})}/>{uiText("这是我的产出")}</label>
      <label className="wide">{uiText("标题（可选）")}<input value={form.title} onChange={(e)=>setForm({...form,title:e.target.value})} placeholder={uiText("留空时使用文件名")}/></label>
    </div><div className="form-actions"><button type="button" className="button secondary" onClick={()=>setUploadOpen(false)}>{uiText("取消")}</button><button className="button primary" disabled={busy}>{busy?<><LoaderCircle className="spin" size={15}/>{uiText("正在保存…")}</>:uiText("保存到知识库")}</button></div></form>}
    <section className="learning-toolbar panel"><label className="search-input"><Search size={16}/><input aria-label={uiText("搜索知识文档")} value={query} onChange={(e)=>setQuery(e.target.value)} placeholder={uiText("搜索标题或文件名…")}/></label><div><select aria-label={uiText("知识项目筛选")} value={project} onChange={(e)=>setProject(e.target.value)}><option value="all">{uiText("全部项目")}</option>{projects.map((row)=><option key={row.id} value={row.id}>{row.name}</option>)}</select><select aria-label={uiText("文档类型筛选")} value={type} onChange={(e)=>setType(e.target.value)}><option value="all">{uiText("全部类型")}</option>{documentTypes.map(([value,label])=><option key={value} value={value}>{uiText(label)}</option>)}</select></div></section>
    {shown.length?<div className="document-grid">{shown.map((row)=><article className="document-card panel" key={row.id}><div className={`document-icon ${row.file_type==="py"||row.file_type==="ts"||row.file_type==="js"?"code":""}`}>{row.file_type==="py"||row.file_type==="ts"||row.file_type==="js"?<FileCode2/>:<FileText/>}</div><div className="document-main"><div><span>{uiText(documentTypes.find(([value])=>value===row.document_type)?.[1]||row.document_type)}</span>{row.is_output&&<b>OUTPUT</b>}<i>{row.processing_status==="ready"?uiText("已解析"):row.processing_status==="failed"?uiText("解析失败"):uiText("处理中")}</i></div><h2>{row.title}</h2><p>{row.original_filename} · {(row.file_size/1024).toFixed(1)} KB</p><footer><span>{dateLabel(row.knowledge_date,true)}</span><span>{projects.find((p)=>p.id===row.project_id)?.name||uiText("未归类")}</span>{row.download_url&&<a href={row.download_url}><Download size={14}/>{uiText("下载")}</a>}</footer></div></article>)}</div>:<div className="panel learning-empty"><FolderOpen size={35}/><h2>{uiText("还没有匹配的资料")}</h2><p>{uiText("上传笔记、代码或课程资料，按知识日期长期保存。")}</p></div>}
  </div>;
}
