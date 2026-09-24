import { api } from "./api";
import { uiText, uiFormat } from "./i18n";

export interface ModelSettings {
  mode: "auto" | "deepseek" | "local";
  model: string;
  num_ctx: number;
  temperature: number;
  think: boolean;
}
export interface AIHealth {
  ollama_available: boolean;
  model_available: boolean;
  model: string;
  busy: boolean;
  error: string | null;
  settings: ModelSettings;
  selected_mode: ModelSettings["mode"];
  providers?: {
    deepseek: { configured: boolean; online: boolean; model: string; error?: string | null };
    local: { configured: boolean; online: boolean; model_available: boolean; model: string; error?: string | null };
  };
}
export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}
export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  status: "generating" | "completed" | "stopped" | "error";
  model?: string;
  duration_ms?: number;
  error?: string | null;
  attachments?: ChatAttachment[];
}
export interface ChatAttachment {
  id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  message_id?: string | null;
  created_at: string;
}
export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}
export interface ChatEvent {
  event:
    | "start"
    | "delta"
    | "reset"
    | "tool_status"
    | "tool_result"
    | "provider_status"
    | "done"
    | "error";
  conversation_id?: string;
  message_id?: string;
  content?: string;
  status?: ChatMessage["status"];
  error?: string | null;
  context_trimmed?: boolean;
  duration_ms?: number;
  tool?: string;
  message?: string;
  success?: boolean;
  affected_entities?: { type: string; id: string }[];
  confirmation?: AgentConfirmation | null;
  provider?: "deepseek" | "local";
  model?: string;
  fallback?: boolean;
}
export interface AgentConfirmation {
  action_id: string;
  tool: string;
  arguments: Record<string, unknown>;
  description: string;
  affected_count: number;
}
export interface ToolResult {
  success: boolean;
  message: string;
  affected_entities: { type: string; id: string }[];
  error_code?: string | null;
}

export async function aiRequest<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  try {
    return await api<T>(`/ai${path}`, {
      signal: AbortSignal.timeout(10000),
      ...options,
    });
  } catch (error) {
    if (
      error instanceof TypeError ||
      (error instanceof DOMException && error.name === "TimeoutError")
    )
      throw new Error(uiText("无法连接 AI 后端或请求超时，请确认项目已启动。"));
    throw error;
  }
}

export async function streamChat(
  conversation_id: string,
  message: string,
  attachment_ids: string[],
  signal: AbortSignal,
  receive: (event: ChatEvent) => void,
) {
  const response = await fetch("/api/ai/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({ conversation_id, message, attachment_ids, stream: true }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : uiFormat("聊天请求失败（{0}）", response.status),
    );
  }
  if (!response.body) throw new Error(uiText("浏览器无法读取流式回答。"));
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "",
    finished = false;
  try {
    let ended = false;
    while (!ended) {
      const { value, done } = await reader.read();
      ended = done;
      buffer += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data: "))
          .map((line) => line.slice(6))
          .join("\n");
        if (!data) continue;
        const event = JSON.parse(data) as ChatEvent;
        receive(event);
        if (event.event === "done" || event.event === "error") finished = true;
      }
    }
    if (!finished)
      throw new Error(uiText("回答连接中断，请刷新历史查看已保存的部分内容。"));
  } finally {
    reader.releaseLock();
  }
}
