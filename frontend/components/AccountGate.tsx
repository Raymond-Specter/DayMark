"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { LogOut, ArrowRight, LoaderCircle } from "lucide-react";
import { api, send } from "@/lib/api";
import { loadLanguage, uiText } from "@/lib/i18n";

type User = { id: string; username: string };
type Session = { mode: "local" | "cloud"; user: User | null };
const AccountContext = createContext({ cloud: false, user: null as User | null, logout: async () => {} });
export const useAccount = () => useContext(AccountContext);

export function SignOut() {
  const { cloud, logout } = useAccount();
  return cloud ? <button className="icon-button" title={uiText("退出登录")} aria-label={uiText("退出登录")} onClick={() => void logout()}><LogOut size={17} /></button> : null;
}

export default function AccountGate({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try { setSession(await api<Session>("/auth/session", { cache: "no-store" })); setError(""); }
    catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => {
    loadLanguage();
    void refresh();
    const expired = () => { setSession(null); void refresh(); };
    window.addEventListener("daymark-session-expired", expired);
    return () => window.removeEventListener("daymark-session-expired", expired);
  }, [refresh]);
  async function logout() {
    try { await send("/auth/logout", {}); setSession({ mode: "cloud", user: null }); }
    catch (e) { setError((e as Error).message); }
  }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      const user = await send<User>(`/auth/${register ? "register" : "login"}`, {
        username: String(form.get("username")), password: String(form.get("password")),
        ...(register ? { invite_code: String(form.get("invite_code")) } : {}),
      });
      setSession({ mode: "cloud", user });
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  if (session && (session.mode === "local" || session.user)) {
    return <AccountContext.Provider value={{ cloud: session.mode === "cloud", user: session.user, logout }}>{error && <p className="account-error" role="alert">{error}</p>}{children}</AccountContext.Provider>;
  }
  return <main className="account-screen">
    <div className="account-intro"><span className="account-wordmark">DAYMARK.</span><h1>{uiText("给每一天，留一点空间。")}</h1><span>PLAN YOUR DAY. KEEP YOUR PROGRESS.</span></div>
    <section className="account-card panel">
      {!session ? <><h2>{uiText("连接 DayMark")}</h2>{error ? <><p role="alert">{error}</p><button className="button" onClick={() => void refresh()}>{uiText("重新连接")}</button></> : <LoaderCircle className="spin" size={24} />}</> : <>
        <h2>{uiText(register ? "创建账号" : "欢迎回来")}</h2>
        <form onSubmit={submit}>
          <label>{uiText("用户名")}<input name="username" autoComplete="username" required pattern="[a-zA-Z0-9_]{3,32}" minLength={3} maxLength={32} title={uiText("3–32 位字母、数字或下划线")} /></label>
          <label>{uiText("密码")}<input name="password" type="password" autoComplete={register ? "new-password" : "current-password"} required minLength={12} maxLength={128} placeholder={uiText("至少 12 个字符")} /></label>
          {register && <label>{uiText("邀请码")}<input name="invite_code" type="password" autoComplete="off" required minLength={16} maxLength={200} /></label>}
          {error && <p role="alert" className="account-error">{error}</p>}
          <button className="button primary" disabled={busy}>{uiText(register ? "创建账号" : "登录")}{busy ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}</button>
        </form>
        <button className="account-switch" disabled={busy} onClick={() => { setRegister(!register); setError(""); }}>{uiText(register ? "已有账号？登录" : "有邀请码？创建账号")}</button>
      </>}
    </section>
  </main>;
}
