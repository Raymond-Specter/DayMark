"use client";
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { aiRequest, type ModelSettings } from "@/lib/ai";

export default function ModelSettingsDrawer({
  value,
  close,
  saved,
}: {
  value: ModelSettings;
  close: () => void;
  saved: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState(value);
  const [models, setModels] = useState<{ name: string }[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    dialog.current?.showModal();
    aiRequest<{ name: string }[]>("/models")
      .then(setModels)
      .catch((e) => setError(e.message));
  }, []);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await aiRequest("/settings", {
        method: "PUT",
        body: JSON.stringify(draft),
      });
      saved();
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog ref={dialog} className="ai-settings-drawer" onCancel={close}>
      <form onSubmit={save}>
        <div className="ai-drawer-heading">
          <div>
            <span className="eyebrow">LOCAL MODEL</span>
            <h2>模型设置</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="关闭模型设置"
            onClick={close}
          >
            <X size={20} />
          </button>
        </div>
        <p>设置保存在本机，下次对话自动沿用。每次仅生成一个回答。</p>
        <label>
          Model
          <select
            value={draft.model}
            onChange={(e) => setDraft({ ...draft, model: e.target.value })}
          >
            {[
              ...new Set([
                draft.model,
                ...models
                  .filter((m) => !m.name.includes("cloud"))
                  .map((m) => m.name),
              ]),
            ].map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <label>
          Context Length
          <select
            value={draft.num_ctx}
            onChange={(e) =>
              setDraft({ ...draft, num_ctx: Number(e.target.value) })
            }
          >
            {[...new Set([2048, 4096, 8192, draft.num_ctx])]
              .sort((a, b) => a - b)
              .map((n) => (
                <option key={n} value={n}>
                  {n.toLocaleString()} tokens
                </option>
              ))}
          </select>
        </label>
        <small>8GB 显存默认 8192；出现显存压力时可降至 4096。</small>
        <label>
          Temperature · {draft.temperature}
          <input
            type="range"
            min="0"
            max="2"
            step="0.1"
            value={draft.temperature}
            onChange={(e) =>
              setDraft({ ...draft, temperature: Number(e.target.value) })
            }
          />
        </label>
        <label>
          Thinking Mode
          <select
            value={String(draft.think)}
            onChange={(e) =>
              setDraft({ ...draft, think: e.target.value === "true" })
            }
          >
            <option value="false">Off · 日常对话</option>
            <option value="true">On · 更多思考时间</option>
          </select>
        </label>
        <small>
          开启后仍只显示最终回答，不展示内部推理内容；可能需要更长等待时间。
        </small>
        {error && (
          <p className="ai-error" role="alert">
            {error}
          </p>
        )}
        <button className="button primary" disabled={busy}>
          {busy ? "保存中…" : "保存设置"}
        </button>
      </form>
    </dialog>
  );
}
