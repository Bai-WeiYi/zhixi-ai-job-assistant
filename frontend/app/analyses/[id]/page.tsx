"use client";

import Link from "next/link";
import { ArrowLeft, LoaderCircle } from "lucide-react";
import { use, useEffect, useState } from "react";

import { AnalysisResultView } from "@/components/analysis-result";
import { getAnalysis } from "@/lib/api";
import type { AnalysisResponse } from "@/lib/types";

export default function AnalysisDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  function loadAnalysis() {
    setLoading(true);
    setError("");
    return getAnalysis(id)
      .then(setAnalysis)
      .catch((reason) => {
        setAnalysis(null);
        setError(reason instanceof Error ? reason.message : "加载失败");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    void loadAnalysis();
  }, [id]);

  return (
    <main className="content-shell detail-shell">
      <Link className="back-link" href="/history">
        <ArrowLeft size={17} /> 返回历史记录
      </Link>
      {error ? (
        <div className="center-state state-column">
          <strong>分析记录加载失败</strong>
          <span>{error}</span>
          <div className="state-actions">
            <button className="secondary-button" onClick={() => void loadAnalysis()} type="button">
              重新加载
            </button>
            <Link className="secondary-link" href="/history">
              返回历史记录
            </Link>
          </div>
        </div>
      ) : null}
      {loading ? (
        <div className="center-state">
          <LoaderCircle className="spin" />
          正在读取分析...
        </div>
      ) : null}
      {analysis ? <AnalysisResultView analysis={analysis} /> : null}
    </main>
  );
}
