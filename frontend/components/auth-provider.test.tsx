import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import {
  AuthProvider,
  isSafeNextPath,
  useAuth,
} from "@/components/auth-provider";
import {
  clearAccessToken,
  getAccessToken,
  getCurrentUser,
  loginUser,
  registerUser,
  setAccessToken,
} from "@/lib/api";

const replace = vi.fn();
let pathname = "/login";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/api", () => ({
  clearAccessToken: vi.fn(),
  getAccessToken: vi.fn(),
  getCurrentUser: vi.fn(),
  loginUser: vi.fn(),
  registerUser: vi.fn(),
  setAccessToken: vi.fn(),
}));

const user = {
  id: 1,
  email: "user@example.com",
  created_at: "2026-06-12T00:00:00Z",
};

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <span>{auth.user?.email ?? "未登录"}</span>
      <button onClick={() => void auth.login("user@example.com", "password123", "/history")}>
        登录
      </button>
      <button
        onClick={() => void auth.register("new@example.com", "password123", "/")}
      >
        注册
      </button>
      <button onClick={auth.logout}>退出</button>
    </div>
  );
}

beforeEach(() => {
  pathname = "/login";
  replace.mockReset();
  vi.mocked(getAccessToken).mockReturnValue(null);
  vi.mocked(getCurrentUser).mockReset();
  vi.mocked(loginUser).mockReset();
  vi.mocked(registerUser).mockReset();
  vi.mocked(setAccessToken).mockReset();
  vi.mocked(clearAccessToken).mockReset();
});

afterEach(cleanup);

it("登录和退出会更新用户及令牌状态", async () => {
  vi.mocked(loginUser).mockResolvedValue({
    access_token: "login-token",
    token_type: "bearer",
    user,
  });
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );

  fireEvent.click(screen.getByRole("button", { name: "登录" }));
  await screen.findByText("user@example.com");
  expect(setAccessToken).toHaveBeenCalledWith("login-token");
  expect(replace).toHaveBeenCalledWith("/history");

  fireEvent.click(screen.getByRole("button", { name: "退出" }));
  expect(clearAccessToken).toHaveBeenCalledOnce();
  expect(replace).toHaveBeenCalledWith("/login");
});

it("注册成功后直接建立登录状态", async () => {
  vi.mocked(registerUser).mockResolvedValue({
    access_token: "register-token",
    token_type: "bearer",
    user: { ...user, email: "new@example.com" },
  });
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );

  fireEvent.click(screen.getByRole("button", { name: "注册" }));
  await screen.findByText("new@example.com");
  expect(setAccessToken).toHaveBeenCalledWith("register-token");
  expect(replace).toHaveBeenCalledWith("/");
});

it("受保护页面会恢复已有登录状态", async () => {
  pathname = "/";
  vi.mocked(getAccessToken).mockReturnValue("saved-token");
  vi.mocked(getCurrentUser).mockResolvedValue(user);

  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );

  expect(screen.getByText("正在确认登录状态...")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("user@example.com")).toBeInTheDocument());
});

it("登录后跳转只允许站内绝对路径", () => {
  expect(isSafeNextPath("/history")).toBe(true);
  expect(isSafeNextPath("//example.com")).toBe(false);
  expect(isSafeNextPath("/\\example.com")).toBe(false);
  expect(isSafeNextPath("https://example.com")).toBe(false);
});
