"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  clearAccessToken,
  getAccessToken,
  getCurrentUser,
  loginUser,
  registerUser,
  setAccessToken,
} from "@/lib/api";
import type { User } from "@/lib/types";

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, nextPath?: string) => Promise<void>;
  register: (email: string, password: string, nextPath?: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const PUBLIC_PATHS = new Set(["/login", "/register"]);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      if (!getAccessToken()) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const currentUser = await getCurrentUser();
        if (!cancelled) setUser(currentUser);
      } catch {
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    function handleUnauthorized() {
      setUser(null);
      setLoading(false);
    }

    window.addEventListener("auth:unauthorized", handleUnauthorized);
    void restoreSession();
    return () => {
      cancelled = true;
      window.removeEventListener("auth:unauthorized", handleUnauthorized);
    };
  }, []);

  useEffect(() => {
    if (!loading && !user && !PUBLIC_PATHS.has(pathname)) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, pathname, router, user]);

  async function authenticate(
    action: typeof loginUser,
    email: string,
    password: string,
    nextPath = "/",
  ) {
    const result = await action(email, password);
    setAccessToken(result.access_token);
    setUser(result.user);
    router.replace(nextPath.startsWith("/") ? nextPath : "/");
  }

  function logout() {
    clearAccessToken();
    setUser(null);
    router.replace("/login");
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      login: (email, password, nextPath) =>
        authenticate(loginUser, email, password, nextPath),
      register: (email, password, nextPath) =>
        authenticate(registerUser, email, password, nextPath),
      logout,
    }),
    [user, loading],
  );

  const isPublic = PUBLIC_PATHS.has(pathname);
  if (!isPublic && (loading || !user)) {
    return (
      <main className="auth-loading" aria-live="polite">
        正在确认登录状态...
      </main>
    );
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth 必须在 AuthProvider 内使用");
  }
  return context;
}
