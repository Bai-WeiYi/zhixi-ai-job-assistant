"use client";

import { FormEvent, useEffect, useState } from "react";
import { BookOpen, FileText, LoaderCircle, Trash2, Upload } from "lucide-react";

import {
  createKnowledgeDocument,
  deleteKnowledgeDocument,
  getUsage,
  listKnowledgeDocuments,
} from "@/lib/api";
import type { KnowledgeDocument, UsageSummary } from "@/lib/types";

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  function loadDocuments() {
    setLoading(true);
    setError("");
    return Promise.all([listKnowledgeDocuments(), getUsage()])
      .then(([items, summary]) => {
        setDocuments(items);
        setUsage(summary);
      })
      .catch((reason) => {
        setError(reason instanceof Error ? reason.message : "知识资料加载失败");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    void loadDocuments();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    if ((file && text.trim()) || (!file && !text.trim())) {
      setError("请在上传 PDF 和粘贴文本中选择一种");
      return;
    }

    setSubmitting(true);
    try {
      const document = await createKnowledgeDocument(title, text, file);
      setDocuments((current) => [document, ...current]);
      setTitle("");
      setText("");
      setFile(null);
      setSuccess(`《${document.title}》已完成解析和向量化。`);
      void getUsage().then(setUsage).catch(() => undefined);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "知识资料上传失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(document: KnowledgeDocument) {
    if (!window.confirm(`确定删除《${document.title}》吗？历史评分中的引用仍会保留。`)) {
      return;
    }
    setDeletingId(document.id);
    setError("");
    setSuccess("");
    try {
      await deleteKnowledgeDocument(document.id);
      setDocuments((current) => current.filter((item) => item.id !== document.id));
      setSuccess("知识资料已删除。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="content-shell knowledge-page">
      <section className="knowledge-heading">
        <div>
          <p className="section-label">RAG 知识库</p>
          <h1>让面试评分参考你的资料</h1>
          <p>上传公司规范、技术笔记或面试标准，答题时会自动检索相关片段。</p>
        </div>
        <div className="knowledge-quota">
          <strong>{documents.length}/10</strong>
          <span>已保存资料</span>
          <small>
            今日可上传{" "}
            {usage ? `${usage.knowledge.remaining}/${usage.knowledge.limit}` : "--"} 次
          </small>
        </div>
      </section>

      <form className="knowledge-form" onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="knowledge-title">
          资料标题
        </label>
        <input
          id="knowledge-title"
          maxLength={200}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="例如：后端开发面试评分标准"
          required
          value={title}
        />

        <div className="knowledge-input-grid">
          <div>
            <label className="field-label" htmlFor="knowledge-text">
              粘贴文本
              <span>{text.length}/50000 字</span>
            </label>
            <textarea
              disabled={Boolean(file)}
              id="knowledge-text"
              maxLength={50000}
              onChange={(event) => setText(event.target.value)}
              placeholder="粘贴技术规范、面试要求或学习资料，至少 30 个字符..."
              rows={9}
              value={text}
            />
          </div>
          <div className="knowledge-upload">
            <FileText size={28} />
            <strong>或上传带文字层的 PDF</strong>
            <p>最大 8 MB，扫描图片版暂不支持 OCR。</p>
            <label className="secondary-button" htmlFor="knowledge-file">
              <Upload size={16} />
              {file ? "重新选择" : "选择 PDF"}
            </label>
            <input
              accept="application/pdf,.pdf"
              id="knowledge-file"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                if (event.target.files?.[0]) setText("");
              }}
              type="file"
            />
            {file ? <span className="selected-file">{file.name}</span> : null}
          </div>
        </div>

        {error ? <div className="error-message">{error}</div> : null}
        {success ? <div className="success-message">{success}</div> : null}
        <button className="primary-button" disabled={submitting} type="submit">
          {submitting ? <LoaderCircle className="spin" size={18} /> : <BookOpen size={18} />}
          {submitting ? "正在切块并生成向量..." : "加入知识库"}
        </button>
      </form>

      <section className="knowledge-list-section">
        <div>
          <p className="section-label">我的资料</p>
          <h2>已向量化的知识文档</h2>
        </div>
        {loading ? (
          <div className="center-state">
            <LoaderCircle className="spin" />
            正在读取知识库...
          </div>
        ) : documents.length === 0 ? (
          <div className="center-state">还没有资料，上传后面试评分会自动使用 RAG。</div>
        ) : (
          <div className="knowledge-list">
            {documents.map((document) => (
              <article key={document.id}>
                <div className="knowledge-icon">
                  <FileText size={20} />
                </div>
                <div>
                  <h3>{document.title}</h3>
                  <p>
                    {document.source_type === "pdf" ? document.filename : "粘贴文本"}
                  </p>
                  <span>
                    {document.character_count.toLocaleString()} 字 · {document.chunk_count} 个片段
                    {" · "}
                    {new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(
                      new Date(document.created_at),
                    )}
                  </span>
                </div>
                <button
                  aria-label="删除知识资料"
                  className="icon-button"
                  disabled={deletingId !== null}
                  onClick={() => handleDelete(document)}
                  type="button"
                >
                  {deletingId === document.id ? (
                    <LoaderCircle className="spin" size={18} />
                  ) : (
                    <Trash2 size={18} />
                  )}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
