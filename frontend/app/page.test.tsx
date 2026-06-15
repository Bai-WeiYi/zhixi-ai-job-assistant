import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";
import { createAnalysis, parseResume } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  createAnalysis: vi.fn(),
  getUsage: vi.fn().mockResolvedValue({
    analysis: { used: 0, limit: 3, remaining: 3, reset_at: "2026-06-13T00:00:00Z" },
    interview: { used: 0, limit: 10, remaining: 10, reset_at: "2026-06-13T00:00:00Z" },
  }),
  parseResume: vi.fn(),
  listInterviewAttempts: vi.fn().mockResolvedValue([]),
  createInterviewAttempt: vi.fn(),
}));

const analysis = {
  id: 3,
  model_name: "test",
  prompt_version: "analysis-v2",
  duration_ms: 1000,
  prompt_tokens: 10,
  completion_tokens: 20,
  total_tokens: 30,
  created_at: "2026-06-12T00:00:00Z",
  result: {
    match_score: 85,
    summary: "整体匹配，具备完整 AI 应用项目经验。",
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

describe("HomePage", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.mocked(createAnalysis).mockReset();
    vi.mocked(parseResume).mockReset();
  });

  it("提交分析后保留输入并显示成功状态", async () => {
    vi.mocked(createAnalysis).mockResolvedValue(analysis);
    render(<HomePage />);

    const resume = "我是一名 Python 开发者，熟悉 FastAPI、SQLAlchemy 和大模型应用开发。";
    const jd = "负责开发 AI 应用，要求掌握 Python、FastAPI、SQL、模型 API 和前端联调能力。";
    fireEvent.change(screen.getByLabelText(/简历内容/), { target: { value: resume } });
    fireEvent.change(screen.getByLabelText(/职位描述/), { target: { value: jd } });
    fireEvent.click(screen.getByRole("button", { name: "开始分析" }));

    await waitFor(() => expect(screen.getByText("整体匹配，具备完整 AI 应用项目经验。")).toBeInTheDocument());
    expect(screen.getByText("分析已完成并保存，可以在历史记录中再次查看。")).toBeInTheDocument();
    expect(screen.getByLabelText(/简历内容/)).toHaveValue(resume);
    expect(screen.getByLabelText(/职位描述/)).toHaveValue(jd);
  });

  it("PDF 解析成功后显示页数和字符数", async () => {
    vi.mocked(parseResume).mockResolvedValue({
      text: "这是从 PDF 中提取的简历正文，包含 Python、FastAPI 和数据库项目经验。",
      page_count: 2,
      character_count: 1280,
    });
    render(<HomePage />);

    const file = new File(["pdf"], "resume.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/上传 PDF 简历/), {
      target: { files: [file] },
    });

    await waitFor(() =>
      expect(screen.getByText("PDF 提取成功：2 页，共 1280 个字符")).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/简历内容/)).toHaveValue(
      "这是从 PDF 中提取的简历正文，包含 Python、FastAPI 和数据库项目经验。",
    );
  });
});
