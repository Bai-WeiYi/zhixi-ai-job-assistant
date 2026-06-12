import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Suspense } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AnalysisDetailPage from "@/app/analyses/[id]/page";
import { getAnalysis } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getAnalysis: vi.fn(),
  getUsage: vi.fn().mockResolvedValue({
    analysis: { used: 0, limit: 3, remaining: 3, reset_at: "2026-06-13T00:00:00Z" },
    interview: { used: 0, limit: 10, remaining: 10, reset_at: "2026-06-13T00:00:00Z" },
  }),
  listInterviewAttempts: vi.fn().mockResolvedValue([]),
  createInterviewAttempt: vi.fn(),
}));

const analysis = {
  id: 9,
  model_name: "demo-local",
  duration_ms: 1000,
  prompt_tokens: 10,
  completion_tokens: 20,
  total_tokens: 30,
  created_at: "2026-06-12T00:00:00Z",
  result: {
    match_score: 86,
    summary: "重新加载后成功显示分析详情。",
    strengths: ["Python"],
    gaps: ["部署"],
    resume_suggestions: ["补充指标"],
    interview_questions: Array.from({ length: 8 }, (_, index) => ({
      question: `详情问题 ${index + 1}`,
      purpose: "考察理解",
      answer_points: ["背景", "结果"],
    })),
  },
};

describe("AnalysisDetailPage", () => {
  afterEach(cleanup);

  it("详情加载失败后可以重试", async () => {
    vi.mocked(getAnalysis)
      .mockRejectedValueOnce(new Error("记录读取失败"))
      .mockResolvedValueOnce(analysis);

    await act(async () => {
      render(
        <Suspense fallback={<div>页面准备中</div>}>
          <AnalysisDetailPage params={Promise.resolve({ id: "9" })} />
        </Suspense>,
      );
    });

    await waitFor(() => expect(screen.getByText("记录读取失败")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));

    await waitFor(() => expect(screen.getByText("重新加载后成功显示分析详情。")).toBeInTheDocument());
    expect(getAnalysis).toHaveBeenCalledTimes(2);
  });
});
