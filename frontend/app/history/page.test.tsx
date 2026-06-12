import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HistoryPage from "@/app/history/page";
import { deleteAnalysis, listAnalyses } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  listAnalyses: vi.fn(),
  deleteAnalysis: vi.fn(),
}));

const item = {
  id: 5,
  match_score: 86,
  summary: "项目经历与岗位要求较为匹配。",
  job_description_preview: "AI 应用全栈工程师",
  model_name: "demo-local",
  created_at: "2026-06-12T00:00:00Z",
};

describe("HistoryPage", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.mocked(listAnalyses).mockReset();
    vi.mocked(deleteAnalysis).mockReset();
  });

  it("加载失败后可以重新读取历史记录", async () => {
    vi.mocked(listAnalyses)
      .mockRejectedValueOnce(new Error("后端暂时不可用"))
      .mockResolvedValueOnce([item]);
    render(<HistoryPage />);

    await waitFor(() => expect(screen.getByText("后端暂时不可用")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));

    await waitFor(() => expect(screen.getByText("AI 应用全栈工程师")).toBeInTheDocument());
    expect(listAnalyses).toHaveBeenCalledTimes(2);
  });

  it("确认后删除记录并显示成功提示", async () => {
    vi.mocked(listAnalyses).mockResolvedValue([item]);
    vi.mocked(deleteAnalysis).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<HistoryPage />);

    await waitFor(() => expect(screen.getByText("AI 应用全栈工程师")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "删除分析" }));

    await waitFor(() => expect(screen.getByText("分析记录已删除。")).toBeInTheDocument());
    expect(deleteAnalysis).toHaveBeenCalledWith(5);
    expect(screen.queryByText("AI 应用全栈工程师")).not.toBeInTheDocument();
  });
});
