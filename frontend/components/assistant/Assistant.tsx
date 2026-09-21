"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  ArrowUp,
  Check,
  Cpu,
  LoaderCircle,
  MessageSquare,
  FileText,
  Paperclip,
  Plus,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Square,
  Trash2,
  X,
} from "lucide-react";
import {
  aiRequest,
  streamChat,
  type AIHealth,
  type AgentConfirmation,
  type ChatEvent,
  type ChatAttachment,
  type ChatMessage,
  type Conversation,
  type ConversationDetail,
} from "@/lib/ai";
import ModelSettingsDrawer from "./ModelSettingsDrawer";
import "./assistant.css";

export default function Assistant({ changed }: { changed?: () => void }) {
  const [health, setHealth] = useState<AIHealth | null>(null);
  const [healthError, setHealthError] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [debug, setDebug] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [actionStatus, setActionStatus] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<AgentConfirmation | null>(null);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const scroll = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const deleteDialog = useRef<HTMLDialogElement>(null);
  const controller = useRef<AbortController | null>(null);
  const activeId = useRef<string | null>(null);
  const requestId = useRef(0);
  const sending = useRef(false);
  useEffect(() => {
    if (deleteId) deleteDialog.current?.showModal();
  }, [deleteId]);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await aiRequest<AIHealth>("/health"));
      setHealthError("");
    } catch (e) {
      setHealth(null);
      setHealthError((e as Error).message);
    }
  }, []);
  const refreshList = useCallback(async () => {
    setConversations(await aiRequest<Conversation[]>("/conversations"));
  }, []);
  function remember(id: string | null) {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("conversation", id);
    else url.searchParams.delete("conversation");
    window.history.replaceState(null, "", url);
  }
  async function loadConversation(id: string) {
    const sequence = ++requestId.current;
    setLoadingHistory(true);
    setError("");
    try {
      const detail = await aiRequest<ConversationDetail>(
        `/conversations/${id}`,
      );
      if (sequence !== requestId.current) return;
      setSelected(id);
      setAttachments([]);
      activeId.current = id;
      setMessages(detail.messages);
      remember(id);
    } catch (e) {
      if (sequence === requestId.current) setError((e as Error).message);
    } finally {
      if (sequence === requestId.current) setLoadingHistory(false);
    }
  }
  useEffect(() => {
    void refreshHealth();
    void refreshList().catch((e) => setError(e.message));
    const id = new URL(window.location.href).searchParams.get("conversation");
    if (id) void loadConversation(id);
    const timer = setInterval(() => {
      void refreshHealth();
    }, 15000);
    return () => {
      clearInterval(timer);
      requestId.current++;
      controller.current?.abort();
      if (sending.current && activeId.current) {
        void fetch(`/api/ai/conversations/${activeId.current}/stop`, {
          method: "POST",
          keepalive: true,
        });
      }
    };
  }, [refreshHealth, refreshList]);
  useEffect(() => {
    if (scroll.current)
      scroll.current.scrollTop = messages.length
        ? scroll.current.scrollHeight
        : 0;
  }, [messages, notice]);

  function newChat() {
    requestId.current++;
    setLoadingHistory(false);
    setSelected(null);
    activeId.current = null;
    setMessages([]);
    setError("");
    setNotice("");
    setActionStatus([]);
    setConfirmation(null);
    setInput("");
    setAttachments([]);
    remember(null);
  }
  async function send() {
    const pendingAttachments = attachments;
    const text = input.trim() || (pendingAttachments.length ? "请阅读并分析附件。" : "");
    if (!text || sending.current || loadingHistory || uploading) return;
    sending.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    setActionStatus([]);
    setConfirmation(null);
    let id = selected;
    const placeholder = `assistant-${Date.now()}`;
    let accepted = false;
    controller.current = new AbortController();
    try {
      if (!id) {
        const conversation = await aiRequest<Conversation>("/conversations", {
          method: "POST",
          body: JSON.stringify({}),
        });
        id = conversation.id;
        setSelected(id);
        activeId.current = id;
        remember(id);
      }
      setInput("");
      setAttachments([]);
      setMessages((old) => [
        ...old,
        {
          id: `user-${Date.now()}`,
          role: "user",
          content: text,
          status: "completed",
          attachments: pendingAttachments,
        },
        {
          id: placeholder,
          role: "assistant",
          content: "",
          status: "generating",
        },
      ]);
      await streamChat(
        id,
        text,
        pendingAttachments.map((item) => item.id),
        controller.current.signal,
        (event: ChatEvent) => {
          if (event.event === "start") {
            accepted = true;
            if (event.context_trimmed)
              setNotice(
                "本次回答使用最近的完整对话；更早的聊天记录仍完整保存在历史中。",
              );
            return;
          }
          if (event.event === "tool_status") {
            setActionStatus((old) => [...old, event.message || "正在执行操作…"]);
            return;
          }
          if (event.event === "tool_result") {
            setActionStatus((old) => [
              ...old,
              `${event.success ? "✓" : "!"} ${event.message || "操作已处理"}`,
            ]);
            if (event.confirmation) setConfirmation(event.confirmation);
            if (event.affected_entities?.length) changed?.();
            return;
          }
          setMessages((old) =>
            old.map((m) =>
              m.id !== placeholder
                ? m
                : {
                    ...m,
                    content:
                      event.event === "reset"
                        ? ""
                        : event.event === "delta"
                        ? m.content + (event.content || "")
                        : (event.content ?? m.content),
                    status: event.status || m.status,
                    duration_ms: event.duration_ms,
                    error: event.error,
                  },
            ),
          );
          if (event.event === "error")
            setError(event.error || "模型生成失败，请重试。");
          if (event.confirmation) setConfirmation(event.confirmation);
          if (event.affected_entities?.length) changed?.();
        },
      );
    } catch (e) {
      if (!accepted) {
        setInput(text === "请阅读并分析附件。" ? "" : text);
        setAttachments(pendingAttachments);
      }
      if (!(e instanceof DOMException && e.name === "AbortError"))
        setError(
          e instanceof TypeError
            ? "聊天连接中断，请确认后端已启动。"
            : (e as Error).message,
        );
    } finally {
      // The server is authoritative, including stopped/error partial responses.
      if (id) {
        try {
          const detail = await aiRequest<ConversationDetail>(
            `/conversations/${id}`,
          );
          setMessages(detail.messages);
        } catch {
          setNotice("暂时无法刷新聊天记录，请稍后重新打开此会话。");
        }
      }
      sending.current = false;
      controller.current = null;
      setBusy(false);
      setStopping(false);
      void refreshList().catch((e) => setError(e.message));
      void refreshHealth();
    }
  }
  async function ensureConversation() {
    if (selected) return selected;
    const conversation = await aiRequest<Conversation>("/conversations", {
      method: "POST",
      body: JSON.stringify({}),
    });
    setSelected(conversation.id);
    activeId.current = conversation.id;
    remember(conversation.id);
    await refreshList();
    return conversation.id;
  }
  async function upload(file: File) {
    if (attachments.length >= 3) {
      setError("每条消息最多上传 3 个文件。");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("文件不能超过 10 MB。");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const id = await ensureConversation();
      const response = await fetch(
        `/api/ai/conversations/${id}/attachments?filename=${encodeURIComponent(file.name)}`,
        { method: "POST", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file },
      );
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : `上传失败（${response.status}）`);
      }
      const attachment = (await response.json()) as ChatAttachment;
      setAttachments((old) => [...old, attachment]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }
  async function removeAttachment(attachment: ChatAttachment) {
    try {
      await aiRequest(`/attachments/${attachment.id}`, { method: "DELETE" });
      setAttachments((old) => old.filter((item) => item.id !== attachment.id));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function stop() {
    if (!activeId.current) return;
    setStopping(true);
    try {
      await aiRequest(`/conversations/${activeId.current}/stop`, {
        method: "POST",
      });
      controller.current?.abort();
    } catch (e) {
      setError((e as Error).message);
      setStopping(false);
    }
  }
  async function remove() {
    if (!deleteId) return;
    try {
      await aiRequest(`/conversations/${deleteId}`, { method: "DELETE" });
      if (selected === deleteId) newChat();
      setDeleteId(null);
      await refreshList();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function resolveConfirmation(approve: boolean) {
    if (!confirmation || !selected) return;
    try {
      const result = await aiRequest<{
        success: boolean;
        message: string;
        affected_entities: { type: string; id: string }[];
      }>(`/confirm/${confirmation.action_id}`, {
        method: "POST",
        body: JSON.stringify({ conversation_id: selected, approve }),
      });
      setActionStatus((old) => [...old, `${result.success ? "✓" : "!"} ${result.message}`]);
      setConfirmation(null);
      if (result.affected_entities?.length) changed?.();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const online = health?.ollama_available && health?.model_available;
  const last = [...messages].reverse().find((m) => m.role === "assistant");
  return (
    <section className="ai-workspace">
      <div className="ai-toolbar">
        <div className="ai-model-label">
          <div className="ai-chip">
            <Cpu size={21} />
          </div>
          <div>
            <strong>{health?.model || "Local AI"}</strong>
            <span>
              <i className={online ? "online" : "offline"} />
              {online
                ? "Online · 本地运行"
                : health?.ollama_available
                  ? "模型未安装"
                  : "Ollama Offline"}
            </span>
          </div>
        </div>
        <div className="ai-toolbar-actions">
          <button
            className="icon-button"
            title="刷新模型状态"
            aria-label="刷新模型状态"
            onClick={refreshHealth}
          >
            <RefreshCw size={17} />
          </button>
          <button
            className="button secondary"
            onClick={() => setSettingsOpen(true)}
            disabled={!health || busy}
          >
            <Settings2 size={16} />
            模型设置
          </button>
        </div>
      </div>
      {(healthError || health?.error) && (
        <div className="ai-offline" role="status">
          <strong>{healthError || health?.error}</strong>
          <span>
            在项目目录运行 <code>.\scripts\setup_ollama.ps1 -Start</code>
            ；首次安装加上 <code>-Install -Pull</code>。
          </span>
          <button onClick={refreshHealth}>重新检查</button>
        </div>
      )}
      <div className="ai-layout">
        <aside className="ai-history">
          <div className="ai-history-heading">
            <span>CONVERSATIONS</span>
            <button
              aria-label="新建对话"
              title="新建对话"
              disabled={busy}
              onClick={newChat}
            >
              <Plus size={19} />
            </button>
          </div>
          <button
            className={`ai-new-chat ${!selected ? "selected" : ""}`}
            disabled={busy}
            onClick={newChat}
          >
            <Plus size={17} />
            开始新对话
          </button>
          <div className="ai-conversation-list">
            {conversations.map((c) => (
              <div
                key={c.id}
                className={`ai-conversation ${selected === c.id ? "selected" : ""}`}
              >
                <button disabled={busy} onClick={() => loadConversation(c.id)}>
                  <MessageSquare size={15} />
                  <span>
                    {c.title}
                    <small>
                      {new Date(c.updated_at).toLocaleDateString("zh-CN", {
                        month: "short",
                        day: "numeric",
                      })}
                    </small>
                  </span>
                </button>
                <button
                  disabled={busy}
                  className="ai-delete"
                  aria-label={`删除对话 ${c.title}`}
                  onClick={() => setDeleteId(c.id)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
          <div className="ai-private">
            <ShieldCheck size={17} />
            <span>
              对话保存在这台电脑
              <br />
              操作通过本机工具与权限记录执行
            </span>
          </div>
        </aside>
        <div className="ai-chat">
          <div
            className="ai-messages"
            ref={scroll}
            aria-label="聊天记录"
            aria-busy={busy}
          >
            {loadingHistory ? (
              <p className="ai-wait">
                <LoaderCircle className="spin" size={18} />
                正在读取历史…
              </p>
            ) : !messages.length ? (
              <div className="ai-welcome">
                <div className="ai-welcome-icon">
                  <MessageSquare size={32} />
                </div>
                <span>YOUR SPACE TO THINK</span>
                <h2>
                  把想法说出来，
                  <br />
                  一起理清下一步。
                </h2>
                <p>
                  与本地 AI 讨论安排、拆解问题。
                  <br />
                  你的目标和节奏，始终由你决定。
                </p>
                <div className="ai-suggestions">
                  {[
                    "帮我理清今天安排的优先顺序",
                    "怎样把一个大目标拆成可执行的小步骤？",
                    "我有几个安排冲突，帮我一起分析",
                  ].map((text) => (
                    <button key={text} onClick={() => setInput(text)}>
                      {text}
                      <ArrowUp size={14} />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages
                .filter((m) => m.role === "user" || m.role === "assistant")
                .map((m) => (
                  <article
                    key={m.id}
                    className={`ai-message ai-message-${m.role}`}
                  >
                    <div className="ai-message-avatar">
                      {m.role === "user" ? "我" : <Cpu size={17} />}
                    </div>
                    <div className="ai-message-body">
                      <strong className="ai-message-author">
                        {m.role === "user" ? "你" : "AI Assistant"}
                      </strong>
                      {m.attachments && m.attachments.length > 0 && (
                        <div className="ai-message-attachments">
                          {m.attachments.map((attachment) => (
                            <a key={attachment.id} href={`/api/ai/attachments/${attachment.id}`}>
                              <FileText size={15} />
                              <span>{attachment.filename}</span>
                            </a>
                          ))}
                        </div>
                      )}
                      {m.content ? (
                        <div className="ai-markdown">
                          <ReactMarkdown
                            skipHtml
                            components={{
                              img: () => null,
                              a: ({ href, children }) => (
                                <a
                                  href={href}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  {children}
                                </a>
                              ),
                            }}
                          >
                            {m.content}
                          </ReactMarkdown>
                        </div>
                      ) : m.status === "generating" ? (
                        <p className="ai-wait">
                          <LoaderCircle size={16} className="spin" />
                          正在准备回答…
                        </p>
                      ) : (
                        <p className="ai-muted">没有生成回答</p>
                      )}
                      {m.status === "stopped" && (
                        <small className="ai-message-state">
                          <Square size={11} />
                          已停止 · 保留部分回答
                        </small>
                      )}
                      {m.status === "error" && (
                        <small className="ai-message-error">
                          {m.error || "回答未完成"}
                        </small>
                      )}
                      {m.status === "completed" && m.role === "assistant" && (
                        <small className="ai-message-state">
                          <Check size={12} />
                          已保存
                        </small>
                      )}
                    </div>
                  </article>
                ))
            )}
          </div>
          <div className="ai-composer-area">
            {actionStatus.length > 0 && (
              <div className="ai-action-status" aria-live="polite">
                {actionStatus.slice(-4).map((status, index) => (
                  <span key={`${status}-${index}`}>{status}</span>
                ))}
              </div>
            )}
            {confirmation && (
              <div className="ai-confirm-action" role="status">
                <strong>AI 准备执行</strong>
                <p>{confirmation.description}</p>
                <small>预计影响 {confirmation.affected_count} 项</small>
                <div>
                  <button className="button secondary" onClick={() => void resolveConfirmation(false)}>
                    取消
                  </button>
                  <button className="button danger" onClick={() => void resolveConfirmation(true)}>
                    确认
                  </button>
                </div>
              </div>
            )}
            {notice && <p className="ai-notice">{notice}</p>}
            {error && (
              <div className="ai-error" role="alert">
                {error}
              </div>
            )}
            {health?.busy && !busy && (
              <p className="ai-notice">另一个页面正在生成回答，请等待完成。</p>
            )}
            <form
              className="ai-composer"
              onSubmit={(e) => {
                e.preventDefault();
                void send();
              }}
            >
              {attachments.length > 0 && (
                <div className="ai-pending-attachments">
                  {attachments.map((attachment) => (
                    <div key={attachment.id}>
                      <FileText size={16} />
                      <span>
                        <strong>{attachment.filename}</strong>
                        <small>{Math.max(1, Math.round(attachment.size_bytes / 1024))} KB</small>
                      </span>
                      <button
                        type="button"
                        aria-label={`移除 ${attachment.filename}`}
                        onClick={() => void removeAttachment(attachment)}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <textarea
                aria-label="给 AI 的消息"
                placeholder="说说你的想法，或需要一起理清的安排…"
                value={input}
                maxLength={12000}
                disabled={busy || loadingHistory}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing
                  ) {
                    e.preventDefault();
                    void send();
                  }
                }}
              />
              <div className="ai-composer-footer">
                <div className="ai-composer-tools">
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".txt,.md,.markdown,.csv,.json,.html,.htm,.css,.js,.jsx,.ts,.tsx,.py,.java,.c,.cpp,.h,.sql,.yaml,.yml,.xml,.log,.pdf,.docx"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) void upload(file);
                    }}
                  />
                  <button
                    type="button"
                    className="ai-attach"
                    title="上传文件"
                    aria-label="上传文件"
                    disabled={busy || loadingHistory || uploading || attachments.length >= 3}
                    onClick={() => fileInput.current?.click()}
                  >
                    {uploading ? <LoaderCircle size={16} className="spin" /> : <Paperclip size={16} />}
                  </button>
                  <span>
                    {uploading
                      ? "正在读取文件…"
                      : busy
                        ? "正在生成 · 仅展示最终回答"
                        : "上传文件 · Enter 发送"}
                  </span>
                </div>
                {busy ? (
                  <button
                    type="button"
                    className="ai-stop"
                    disabled={stopping}
                    onClick={stop}
                  >
                    <Square size={13} />
                    {stopping ? "正在停止…" : "停止生成"}
                  </button>
                ) : (
                  <button
                    type="submit"
                    className="ai-send"
                    aria-label="发送消息"
                    disabled={
                      (!input.trim() && !attachments.length) || loadingHistory || uploading || Boolean(health?.busy)
                    }
                  >
                    <ArrowUp size={20} />
                  </button>
                )}
              </div>
            </form>
            <div className="ai-bottom-note">
              <span>AI 可通过已授权工具操作任务、日历和重复规则。</span>
              <button onClick={() => setDebug(!debug)} aria-expanded={debug}>
                开发者信息
              </button>
            </div>
          </div>
        </div>
      </div>
      {debug && (
        <dl className="ai-debug">
          <div>
            <dt>Ollama</dt>
            <dd>{health?.ollama_available ? "Online" : "Offline"}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{health?.model || "未知"}</dd>
          </div>
          <div>
            <dt>Response time</dt>
            <dd>
              {last?.duration_ms != null
                ? `${(last.duration_ms / 1000).toFixed(2)} s`
                : "—"}
            </dd>
          </div>
          <div>
            <dt>Context</dt>
            <dd>{health?.settings.num_ctx || "—"}</dd>
          </div>
          <div>
            <dt>Thinking</dt>
            <dd>{health?.settings.think ? "On" : "Off"}</dd>
          </div>
          <div>
            <dt>Conversation ID</dt>
            <dd>{selected || "尚未创建"}</dd>
          </div>
        </dl>
      )}
      {settingsOpen && health && (
        <ModelSettingsDrawer
          value={health.settings}
          close={() => setSettingsOpen(false)}
          saved={refreshHealth}
        />
      )}
      {deleteId && (
        <dialog
          ref={deleteDialog}
          onCancel={() => setDeleteId(null)}
          role="alertdialog"
          aria-modal="true"
          aria-label="删除对话确认"
          className="ai-confirm"
        >
          <h2>删除这段对话？</h2>
          <p>会同时删除全部聊天记录，此操作无法撤销。</p>
          <div>
            <button
              className="button secondary"
              onClick={() => setDeleteId(null)}
            >
              保留对话
            </button>
            <button className="button danger" onClick={remove}>
              确认删除
            </button>
          </div>
        </dialog>
      )}
    </section>
  );
}
