import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import KnowledgePage from "@/app/knowledge/page";
import {
  createKnowledgeDocument,
  deleteKnowledgeDocument,
  listKnowledgeDocuments,
} from "@/lib/api";

vi.mock("@/lib/api", () => ({
  listKnowledgeDocuments: vi.fn(),
  createKnowledgeDocument: vi.fn(),
  deleteKnowledgeDocument: vi.fn(),
  getUsage: vi.fn().mockResolvedValue({
    analysis: { used: 0, limit: 3, remaining: 3, reset_at: "2026-06-14T00:00:00Z" },
    interview: { used: 0, limit: 10, remaining: 10, reset_at: "2026-06-14T00:00:00Z" },
    knowledge: { used: 0, limit: 5, remaining: 5, reset_at: "2026-06-14T00:00:00Z" },
  }),
}));

const document = {
  id: 1,
  title: "FastAPI 面试标准",
  source_type: "text" as const,
  filename: null,
  character_count: 1200,
  chunk_count: 3,
  created_at: "2026-06-13T00:00:00Z",
};

describe("KnowledgePage", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([]);
    vi.mocked(createKnowledgeDocument).mockReset();
    vi.mocked(deleteKnowledgeDocument).mockReset();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("上传文本后显示已向量化资料", async () => {
    vi.mocked(createKnowledgeDocument).mockResolvedValue(document);
    render(<KnowledgePage />);
    await waitFor(() => expect(listKnowledgeDocuments).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("资料标题"), {
      target: { value: "FastAPI 面试标准" },
    });
    fireEvent.change(screen.getByLabelText(/粘贴文本/), {
      target: { value: "这是一段用于面试评分的 FastAPI 技术规范和回答标准。".repeat(3) },
    });
    fireEvent.click(screen.getByRole("button", { name: "加入知识库" }));

    await waitFor(() => expect(screen.getByText("FastAPI 面试标准")).toBeInTheDocument());
    expect(screen.getByText(/已完成解析和向量化/)).toBeInTheDocument();
  });

  it("读取并删除已有资料", async () => {
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([document]);
    vi.mocked(deleteKnowledgeDocument).mockResolvedValue(undefined);
    render(<KnowledgePage />);

    await waitFor(() => expect(screen.getByText("FastAPI 面试标准")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "删除知识资料" }));

    await waitFor(() =>
      expect(screen.queryByText("FastAPI 面试标准")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("知识资料已删除。")).toBeInTheDocument();
  });
});
