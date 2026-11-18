import { uiText } from "./i18n";

export interface GuestState {
  version: 1;
  tables: Record<string, Record<string, unknown>[]>;
  files: Record<string, string>;
  api_key: string;
}

const modeKey = "daymark.guest";
const lockName = "daymark-guest-workspace";
let active = false;
let queue: Promise<unknown> = Promise.resolve();
let activeRun: string | null = null;
let unsaved: GuestState | null = null;

export const isGuest = () => active;
export const remembersGuest = () => {
  try { return window.localStorage.getItem(modeKey) === "1"; }
  catch { return false; }
};
const emptyState = (): GuestState => ({ version: 1, tables: {}, files: {}, api_key: "" });

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("daymark-guest", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("workspace");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error(uiText("浏览器无法保存访客记录，请允许此网站使用存储空间。")));
    request.onblocked = () => reject(new Error(uiText("请关闭其他 DayMark 标签页后重试。")));
  });
}

export async function readGuestState(): Promise<GuestState> {
  if (unsaved) return unsaved;
  const db = await database();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction("workspace", "readonly");
    const request = transaction.objectStore("workspace").get("current");
    transaction.oncomplete = () => { db.close(); resolve(request.result || emptyState()); };
    transaction.onerror = () => { db.close(); reject(new Error(uiText("无法读取浏览器中的访客记录。"))); };
  });
}

async function saveGuestState(state: GuestState) {
  unsaved = state;
  const db = await database();
  await new Promise<void>((resolve, reject) => {
    const transaction = db.transaction("workspace", "readwrite");
    transaction.objectStore("workspace").put(state, "current");
    transaction.oncomplete = () => { db.close(); unsaved = null; resolve(); };
    transaction.onabort = transaction.onerror = () => {
      db.close();
      unsaved = state;
      reject(new Error(uiText("访客记录未能保存到浏览器，请先导出备份并检查存储空间，暂勿关闭页面。")));
    };
  });
}

export async function enterGuest() {
  await exclusive(async () => { await saveGuestState(await readGuestState()); });
  window.localStorage.setItem(modeKey, "1");
  active = true;
}

export async function leaveGuest() {
  await stopGuest();
  await exclusive(async () => {
    window.localStorage.removeItem(modeKey);
    active = false;
  });
}

async function exclusive<T>(work: () => Promise<T>): Promise<T> {
  // HTTPS Web Locks also serialize other tabs, preventing lost snapshot updates.
  if (navigator.locks) return await navigator.locks.request(lockName, work);
  const next = queue.then(work, work);
  queue = next.catch(() => {});
  return next;
}

function encode(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 32768)
    binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
  return btoa(binary);
}

function decode(value: string): Uint8Array {
  return Uint8Array.from(atob(value), (character) => character.charCodeAt(0));
}

async function stopGuest() {
  if (!activeRun) return new Response(JSON.stringify({ stopped: false }));
  return fetch("/api/guest/stop", {
    method: "POST", credentials: "omit", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: activeRun }),
  });
}

function needsFiles(path: string, method: string) {
  return path === "/api/ai/chat" || path.startsWith("/api/ai/confirm/")
    || path.includes("/attachments") || path === "/api/documents/upload"
    || path.endsWith("/download") || (method === "DELETE" && path.startsWith("/api/ai/conversations/"));
}

export function workspaceFetch(url: string, options: RequestInit = {}): Promise<Response> {
  if (!active || url.startsWith("/api/auth/")) return fetch(url, options);
  if (/^\/api\/ai\/conversations\/[^/]+\/stop$/.test(url)) return stopGuest();

  return new Promise<Response>((resolve, reject) => {
    void exclusive(async () => {
      options.signal?.throwIfAborted();
      let state = await readGuestState();
      const { api_key, ...records } = state;
      const method = options.method || "GET";
      const path = url.split("?")[0];
      const runId = crypto.randomUUID();
      const body = options.body ? await new Response(options.body).arrayBuffer() : new ArrayBuffer(0);
      const requestBody = JSON.stringify({
        run_id: runId, method, path: url,
        content_type: new Headers(options.headers).get("content-type") || "application/json",
        body: encode(new Uint8Array(body)),
        state: { ...records, files: needsFiles(path, method) ? state.files : {},
          ...(path.startsWith("/api/ai/") ? { api_key } : {}) },
      });
      if (new Blob([requestBody]).size > 128 * 1024 * 1024)
        throw new Error(uiText("访客数据包超过 128 MB，请先导出备份。"));

      activeRun = runId;
      // On stop/unmount, drain the final response so partial chat/tool changes
      // reach IndexedDB before releasing the workspace lock.
      const stop = () => { void stopGuest().catch(() => {}); };
      options.signal?.addEventListener("abort", stop, { once: true });
      const output: { controller?: ReadableStreamDefaultController<Uint8Array> } = {};
      let cancelled = false;
      try {
        const response = await fetch("/api/guest", {
          method: "POST", credentials: "omit", cache: "no-store",
          headers: { "Content-Type": "application/json" }, body: requestBody,
        });
        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          throw new Error(typeof error.detail === "string" ? error.detail : uiText("访客请求失败，请稍后重试。"));
        }
        if (!response.body) throw new Error(uiText("浏览器无法读取访客数据。"));
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let receivedState = false;
        try {
          while (true) {
            const { done, value } = await reader.read();
            buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
              if (!line) continue;
              const frame = JSON.parse(line);
              if (frame.kind === "response") {
                const stream = new ReadableStream<Uint8Array>({
                  start(controller) { output.controller = controller; },
                  cancel() { cancelled = true; stop(); },
                });
                resolve(new Response(frame.status === 204 ? null : stream, { status: frame.status, headers: frame.headers }));
              } else if (frame.kind === "state") {
                state = { ...state, ...frame.state };
                await saveGuestState(state);
                receivedState = true;
              } else if (frame.kind === "body") {
                if (!cancelled) output.controller?.enqueue(decode(frame.data));
              } else if (frame.kind === "error") {
                throw new Error(frame.detail);
              }
            }
            if (done) break;
          }
          if (!receivedState || buffer.trim()) throw new Error(uiText("访客连接中断，已保留最后一次保存的浏览器记录。"));
          if (!cancelled) output.controller?.close();
        } finally {
          reader.releaseLock();
        }
      } catch (error) {
        if (!cancelled) output.controller?.error(error);
        throw error;
      } finally {
        activeRun = null;
        options.signal?.removeEventListener("abort", stop);
      }
    }).catch(reject);
  });
}

export async function guestBackup(): Promise<unknown> {
  return exclusive(async () => {
    const { api_key: _key, ...state } = await readGuestState();
    return { format: "daymark-guest-v1", exported_at: new Date().toISOString(), ...state };
  });
}

export async function downloadWorkspaceFile(url: string, filename?: string) {
  const response = await workspaceFetch(url);
  if (!response.ok) throw new Error(uiText("文件下载失败，请重试。"));
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename || "daymark-export.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
