"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { LoaderCircle, LogIn, UserPlus } from "lucide-react";
import { useSearchParams } from "next/navigation";

import { useAuth } from "@/components/auth-provider";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const searchParams = useSearchParams();
  const { login, register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const isLogin = mode === "login";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const nextPath = searchParams.get("next") ?? "/";
      await (isLogin ? login : register)(email, password, nextPath);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <Link className="auth-brand" href="/">
          <span className="brand-mark">职</span>
          <span>职析</span>
        </Link>
        <div className="auth-heading">
          <span>{isLogin ? "WELCOME BACK" : "CREATE ACCOUNT"}</span>
          <h1>{isLogin ? "登录你的求职工作台" : "创建你的求职工作台"}</h1>
          <p>
            {isLogin
              ? "继续查看岗位分析和模拟面试记录。"
              : "你的分析和练习记录将只属于当前账号。"}
          </p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="email">邮箱</label>
          <input
            autoComplete="email"
            id="email"
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@example.com"
            required
            type="email"
            value={email}
          />

          <label htmlFor="password">密码</label>
          <input
            autoComplete={isLogin ? "current-password" : "new-password"}
            id="password"
            minLength={8}
            maxLength={72}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="至少 8 个字符"
            required
            type="password"
            value={password}
          />

          {error ? <div className="error-message">{error}</div> : null}
          <button className="primary-button" disabled={submitting} type="submit">
            {submitting ? (
              <LoaderCircle className="spin" size={18} />
            ) : isLogin ? (
              <LogIn size={18} />
            ) : (
              <UserPlus size={18} />
            )}
            {submitting ? "正在处理..." : isLogin ? "登录" : "注册并登录"}
          </button>
        </form>

        <p className="auth-switch">
          {isLogin ? "还没有账号？" : "已经有账号？"}
          <Link href={isLogin ? "/register" : "/login"}>
            {isLogin ? "立即注册" : "返回登录"}
          </Link>
        </p>
      </section>
    </main>
  );
}
