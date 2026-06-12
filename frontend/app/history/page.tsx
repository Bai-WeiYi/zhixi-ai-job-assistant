"use client";

import Link from "next/link";
import { LoaderCircle, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { deleteAnalysis, listAnalyses } from "@/lib/api";
import type { AnalysisListItem } from "@/lib/types";

export default function HistoryPage() {
  const [items, setItems] = useState<AnalysisListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);

  function loadAnalyses() {
    setLoading(true);
    setError("");
    return listAnalyses()
      .then(setItems)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "加载失败"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    void loadAnalyses();
  }, []);

  async function handleDelete(id: number) {
    if (!window.confirm("确定删除这条分析吗？相关面试练习记录也会一起删除。")) {
      return;
    }

    setError("");
    setSuccess("");
    setDeletingId(id);
    try {
      await deleteAnalysis(id);
      setItems((current) => current.filter((item) => item.id !== id));
      setSuccess("分析记录已删除。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="content-shell">
      <section className="history-heading">
        <div>
          <h1>历史分析</h1>
          <p>回顾不同岗位的匹配结论与面试准备重点。</p>
        </div>
        <Link className="primary-link" href="/">
          <Plus size={17} /> 新建分析
        </Link>
      </section>

      {error ? (
        <div className="error-message state-message">
          <span>{error}</span>
          <button className="inline-action" onClick={() => void loadAnalyses()} type="button">
            重新加载
          </button>
        </div>
      ) : null}
      {success ? (
        <div className="success-message" role="status">
          {success}
        </div>
      ) : null}
      {loading ? (
        <div className="center-state">
          <LoaderCircle className="spin" />
          正在读取记录...
        </div>
      ) : items.length === 0 ? (
        <div className="center-state">还没有分析记录，先完成一次岗位分析吧。</div>
      ) : (
        <div className="history-list">
          {items.map((item) => (
            <article className="history-row" key={item.id}>
              <div className="history-score">{item.match_score}</div>
              <Link className="history-main" href={`/analyses/${item.id}`}>
                <h2>{item.job_description_preview}</h2>
                <p>{item.summary}</p>
                <span>
                  {new Intl.DateTimeFormat("zh-CN", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(item.created_at))}
                  {" · "}
                  {item.model_name}
                </span>
              </Link>
              <button
                aria-label="删除分析"
                className="icon-button"
                disabled={deletingId !== null}
                onClick={() => handleDelete(item.id)}
                type="button"
              >
                {deletingId === item.id ? (
                  <LoaderCircle className="spin" size={18} />
                ) : (
                  <Trash2 size={18} />
                )}
              </button>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
