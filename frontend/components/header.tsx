"use client";

import Link from "next/link";
import { LogOut } from "lucide-react";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/auth-provider";

export function Header() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  if (pathname === "/login" || pathname === "/register" || !user) {
    return null;
  }

  return (
    <header className="site-header">
      <div className="header-inner">
        <Link className="brand" href="/">
          <span className="brand-mark">职</span>
          <span>职析</span>
        </Link>
        <nav aria-label="主导航">
          <Link href="/">新建分析</Link>
          <Link href="/history">历史记录</Link>
          <span className="header-user" title={user.email}>
            {user.email}
          </span>
          <button className="logout-button" onClick={logout} type="button">
            <LogOut size={15} />
            退出
          </button>
        </nav>
      </div>
    </header>
  );
}
