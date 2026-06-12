import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="auth-loading">正在加载登录页面...</main>}>
      <AuthForm mode="login" />
    </Suspense>
  );
}
