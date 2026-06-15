import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AnalysisResultView } from "@/components/analysis-result";
import { createInterviewAttempt, listInterviewAttempts } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  listInterviewAttempts: vi.fn(),
  createInterviewAttempt: vi.fn(),
  getUsage: vi.fn().mockResolvedValue({
    analysis: { used: 0, limit: 3, remaining: 3, reset_at: "2026-06-13T00:00:00Z" },
    interview: { used: 0, limit: 10, remaining: 10, reset_at: "2026-06-13T00:00:00Z" },
  }),
}));

const analysis = {
  id: 1,
  model_name: "test",
  prompt_version: "analysis-v2",
  duration_ms: 1000,
  prompt_tokens: 10,
  completion_tokens: 20,
  total_tokens: 30,
  created_at: "2026-06-08T00:00:00Z",
  result: {
    match_score: 80,
    summary: "整体匹配，建议继续补足工程实践。",
    strengths: ["Python 基础"],
    gaps: ["部署经验"],
    resume_suggestions: ["补充量化结果"],
    interview_questions: Array.from({ length: 8 }, (_, index) => ({
      question: `问题 ${index + 1}`,
      purpose: "考察理解",
      answer_points: ["背景", "取舍"],
    })),
  },
};

describe("AnalysisResultView", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.mocked(listInterviewAttempts).mockResolvedValue([]);
    vi.mocked(createInterviewAttempt).mockReset();
  });

  it("展示分数和八道面试题", async () => {
    render(<AnalysisResultView analysis={analysis} />);

    expect(screen.getByLabelText("岗位匹配度 80 分")).toBeInTheDocument();
    expect(screen.getByText("问题 8")).toBeInTheDocument();
    await waitFor(() => expect(listInterviewAttempts).toHaveBeenCalledWith(1));
  });

  it("提交回答后展示评分并支持重复练习", async () => {
    vi.mocked(createInterviewAttempt).mockResolvedValue({
      id: 10,
      analysis_id: 1,
      question_number: 1,
      question_text: "问题 1",
      answer_text: "我会先介绍项目背景，再说明技术取舍、实现过程和最终结果。",
      feedback: {
        score: 88,
        summary: "回答结构清楚，能够说明关键技术取舍。",
        strengths: ["结构清楚"],
        improvements: ["补充量化结果"],
        suggested_answer_points: ["背景", "行动", "结果"],
      },
      model_name: "test",
      prompt_version: "interview-v2",
      duration_ms: 500,
      prompt_tokens: 10,
      completion_tokens: 20,
      total_tokens: 30,
      references: [],
      created_at: "2026-06-11T00:00:00Z",
    });
    render(<AnalysisResultView analysis={analysis} />);

    fireEvent.change(screen.getByLabelText(/你的回答/), {
      target: { value: "我会先介绍项目背景，再说明技术取舍、实现过程和最终结果。" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "提交回答并评分" }).closest("form")!);

    await waitFor(() =>
      expect(screen.getByText("回答结构清楚，能够说明关键技术取舍。")).toBeInTheDocument(),
    );
    expect(screen.getAllByText("88")).toHaveLength(2);
    expect(screen.getByText("评分完成：本次 88 分。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "再次提交练习" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("本次评分运行详情"));
    expect(screen.getByText("interview-v2")).toBeInTheDocument();
  });

  it("评分失败时保留回答，切换题目时保留草稿", async () => {
    vi.mocked(createInterviewAttempt).mockRejectedValue(new Error("模型响应超时"));
    render(<AnalysisResultView analysis={analysis} />);

    const answer = "我会先介绍项目背景，再说明技术取舍、实现过程和最终结果。";
    const input = screen.getByLabelText(/你的回答/);
    fireEvent.change(input, { target: { value: answer } });
    fireEvent.submit(screen.getByRole("button", { name: "提交回答并评分" }).closest("form")!);

    await waitFor(() => expect(screen.getByText("模型响应超时")).toBeInTheDocument());
    expect(input).toHaveValue(answer);

    fireEvent.click(screen.getByRole("button", { name: "第 2 题" }));
    expect(input).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "第 1 题" }));
    expect(input).toHaveValue(answer);
  });
});
