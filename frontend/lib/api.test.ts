import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearAccessToken,
  getCurrentUser,
  getUsage,
  listAnalyses,
  setAccessToken,
} from "@/lib/api";

describe("API 鉴权请求", () => {
  beforeEach(() => {
    clearAccessToken();
    vi.restoreAllMocks();
  });

  it("自动携带 Bearer token", async () => {
    setAccessToken("test-token");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await listAnalyses();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/analyses",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
        }),
      }),
    );
  });

  it("令牌失效时清除本地状态并发出通知", async () => {
    setAccessToken("expired-token");
    const listener = vi.fn();
    window.addEventListener("auth:unauthorized", listener);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "登录状态已失效，请重新登录" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(getCurrentUser()).rejects.toThrow("登录状态已失效");
    expect(window.localStorage.getItem("zhixi_access_token_v1")).toBeNull();
    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener("auth:unauthorized", listener);
  });

  it("保留 429 状态和服务端限额提示", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "今日 AI 使用次数已达上限" }), {
        status: 429,
        headers: {
          "Content-Type": "application/json",
          "Retry-After": "3600",
        },
      }),
    );

    await expect(getUsage()).rejects.toMatchObject({
      message: "今日 AI 使用次数已达上限",
      status: 429,
      retryAfter: 3600,
    });
  });

  it("网络不可用时提示免费服务可能正在唤醒", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network"));

    await expect(getUsage()).rejects.toThrow("免费服务首次访问可能需要约一分钟唤醒");
  });
});
