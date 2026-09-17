"use client";

import { useActionState, useState } from "react";
import { login, register, type AuthFormState } from "./actions";

const initialState: AuthFormState = {};
const inputClass =
  "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832] outline-none focus:border-[#0f6b5b] focus:ring-3 focus:ring-[#dff1eb]";

export function AuthForm() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loginState, loginAction, loginPending] = useActionState(login, initialState);
  const [registerState, registerAction, registerPending] = useActionState(register, initialState);
  const state = mode === "login" ? loginState : registerState;
  const pending = mode === "login" ? loginPending : registerPending;

  return (
    <div className="mx-auto max-w-md rounded-2xl border border-[#dce4e0] bg-white p-6 shadow-sm sm:p-8">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">ConnectSphere account</p>
      <h1 className="mt-3 text-3xl font-bold tracking-tight text-[#17211d]">
        {mode === "login" ? "Log in" : "Create an account"}
      </h1>
      <p className="mt-2 text-sm leading-6 text-[#68776f]">
        {mode === "login" ? "Verify your account credentials." : "Sign up with your email and a password."}
      </p>

      <div className="mt-6 flex gap-2" aria-label="Account action">
        <button type="button" onClick={() => setMode("login")} aria-pressed={mode === "login"} className={`rounded-lg px-4 py-2 text-sm font-semibold ${mode === "login" ? "bg-[#0f6b5b] text-white" : "bg-[#eef3f0] text-[#34463f]"}`}>Log in</button>
        <button type="button" onClick={() => setMode("register")} aria-pressed={mode === "register"} className={`rounded-lg px-4 py-2 text-sm font-semibold ${mode === "register" ? "bg-[#0f6b5b] text-white" : "bg-[#eef3f0] text-[#34463f]"}`}>Sign up</button>
      </div>

      <form action={mode === "login" ? loginAction : registerAction} className="mt-6 space-y-5">
        <label className="block text-sm font-semibold text-[#34463f]">
          Email
          <input name="email" type="email" autoComplete="email" required maxLength={254} className={inputClass} />
        </label>
        <label className="block text-sm font-semibold text-[#34463f]">
          Password
          <input name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={8} maxLength={128} className={inputClass} />
        </label>
        {state.message && (
          <p role={state.success ? "status" : "alert"} className={`rounded-xl px-4 py-3 text-sm ${state.success ? "bg-[#e7f5ed] text-[#145d40]" : "bg-[#fff4f3] text-[#8e3d35]"}`}>
            {state.message}
          </p>
        )}
        <button type="submit" disabled={pending} className="min-h-11 w-full rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white transition hover:bg-[#0b5b4d] disabled:opacity-60">
          {pending ? "Please wait..." : mode === "login" ? "Log in" : "Create account"}
        </button>
      </form>
      <p className="mt-5 text-xs leading-5 text-[#718078]">Your session is kept in an HTTP-only browser cookie until it expires or you log out.</p>
    </div>
  );
}
