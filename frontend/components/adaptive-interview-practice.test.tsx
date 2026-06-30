import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InterviewPractice } from "@/components/interview-practice";
import {
  answerAdaptiveTurn,
  createAdaptiveInterview,
  getAdaptiveInterview,
  listAdaptiveInterviews,
} from "@/lib/api";

vi.mock("@/lib/api", () => ({
  answerAdaptiveTurn: vi.fn(),
  createAdaptiveInterview: vi.fn(),
  getAdaptiveInterview: vi.fn(),
  getUsage: vi.fn().mockResolvedValue({
    analysis: { used: 0, limit: 3, remaining: 3, reset_at: "2026-06-21T00:00:00Z" },
    interview: { used: 0, limit: 10, remaining: 10, reset_at: "2026-06-21T00:00:00Z" },
    knowledge: { used: 0, limit: 5, remaining: 5, reset_at: "2026-06-21T00:00:00Z" },
  }),
  listAdaptiveInterviews: vi.fn(),
  listInterviewAttempts: vi.fn().mockResolvedValue([]),
  createInterviewAttempt: vi.fn(),
}));

const analysis = {
  id: 9,
  model_name: "test-model",
  prompt_version: "analysis-v2",
  duration_ms: 100,
  prompt_tokens: 10,
  completion_tokens: 20,
  total_tokens: 30,
  created_at: "2026-06-21T00:00:00Z",
  result: {
    match_score: 82,
    summary: "候选人的技术方向匹配目标岗位。",
    strengths: ["Python"],
    gaps: ["部署"],
    resume_suggestions: ["补充结果"],
    interview_questions: Array.from({ length: 8 }, (_, index) => ({
      question: `主问题 ${index + 1}`,
      purpose: "考察工程判断",
      answer_points: ["背景", "取舍"],
    })),
  },
};

function session(source: "main" | "follow_up" = "main") {
  return {
    id: 3,
    analysis_id: 9,
    status: "awaiting_answer" as const,
    workflow_version: "adaptive-interview-v1",
    max_rounds: 5,
    completed_turns: source === "follow_up" ? 1 : 0,
    current_node: "await_answer",
    current_question: {
      turn_id: source === "follow_up" ? 12 : 11,
      round_number: source === "follow_up" ? 2 : 1,
      source,
      source_question_number: 1,
      question: source === "follow_up" ? "请具体说明失败方案。" : "请说明技术选型。",
      purpose: "考察工程判断",
      answer_points: ["背景", "取舍"],
    },
    turns: source === "follow_up" ? [{
      id: 11,
      round_number: 1,
      source: "main" as const,
      source_question_number: 1,
      question: "请说明技术选型。",
      purpose: "考察工程判断",
      answer_text: "我选择了 FastAPI，但没有比较其他方案。",
      feedback: {
        score: 59,
        summary: "回答了方向，但缺少方案比较。",
        strengths: ["回应了题目"],
        improvements: ["补充方案比较"],
        suggested_answer_points: ["背景", "取舍"],
      },
      model_name: "test-model",
      prompt_version: "adaptive-evaluation-v1",
      duration_ms: 80,
      total_tokens: 30,
      references: [],
      route_decision: "follow_up" as const,
      created_at: "2026-06-21T00:00:00Z",
      answered_at: "2026-06-21T00:01:00Z",
    }] : [],
    report: null,
    execution_path: [{ node: "evaluate_answer", duration_ms: 80, detail: "评分 59，路由到 follow_up" }],
    total_tokens: source === "follow_up" ? 30 : 0,
    duration_ms: source === "follow_up" ? 80 : 0,
    created_at: "2026-06-21T00:00:00Z",
    updated_at: "2026-06-21T00:01:00Z",
    completed_at: null,
  };
}

describe("AdaptiveInterviewPractice", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("从标准练习切换后开始面试，并展示低分追问路径", async () => {
    vi.mocked(listAdaptiveInterviews).mockResolvedValue([]);
    vi.mocked(createAdaptiveInterview).mockResolvedValue(session("main"));
    vi.mocked(answerAdaptiveTurn).mockResolvedValue(session("follow_up"));

    render(<InterviewPractice analysis={analysis} />);
    fireEvent.click(screen.getByRole("button", { name: /LangGraph 自适应面试/ }));
    await waitFor(() => expect(screen.getByText("让下一道题由你的回答决定")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "开始自适应面试" }));
    await waitFor(() => expect(screen.getByText("请说明技术选型。")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/你的回答/), {
      target: { value: "我选择了 FastAPI，但还需要补充候选方案、技术权衡和量化结果。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交本轮回答" }));

    await waitFor(() => expect(screen.getByText("请具体说明失败方案。")).toBeInTheDocument());
    expect(screen.getByText(/进入针对性追问/)).toBeInTheDocument();
    expect(answerAdaptiveTurn).toHaveBeenCalledWith(3, 11, expect.any(String));
  });

  it("可以恢复已有会话", async () => {
    vi.mocked(listAdaptiveInterviews).mockResolvedValue([{ id: 3 } as never]);
    vi.mocked(getAdaptiveInterview).mockResolvedValue(session("follow_up"));

    render(<InterviewPractice analysis={analysis} />);
    fireEvent.click(screen.getByRole("button", { name: /LangGraph 自适应面试/ }));

    await waitFor(() => expect(screen.getByText("请具体说明失败方案。")).toBeInTheDocument());
    expect(getAdaptiveInterview).toHaveBeenCalledWith(3);
    expect(screen.getByText("1/5")).toBeInTheDocument();
  });
});
