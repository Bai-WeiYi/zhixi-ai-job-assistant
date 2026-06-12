import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";

export default function RegisterPage() {
  return (
    <Suspense fallback={<main className="auth-loading">正在加载注册页面...</main>}>
      <AuthForm mode="register" />
    </Suspense>
  );
}
