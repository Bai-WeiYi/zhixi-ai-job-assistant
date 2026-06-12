import { CheckCircle2, CircleAlert, Lightbulb, Target } from "lucide-react";

import { InterviewPractice } from "@/components/interview-practice";
import type { AnalysisResponse } from "@/lib/types";

type Props = {
  analysis: AnalysisResponse;
};

function InsightList({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "positive" | "warning" | "neutral";
}) {
  const Icon = tone === "positive" ? CheckCircle2 : tone === "warning" ? CircleAlert : Lightbulb;
  return (
    <section className={`insight-block ${tone}`}>
      <h3>
        <Icon size={18} aria-hidden />
        {title}
      </h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export function AnalysisResultView({ analysis }: Props) {
  const { result } = analysis;
  return (
    <div className="result-content">
      <section className="score-section">
        <div className="score-ring" aria-label={`岗位匹配度 ${result.match_score} 分`}>
          <strong>{result.match_score}</strong>
          <span>匹配度</span>
        </div>
        <div>
          <p className="section-label">分析结论</p>
          <h2>你与这个岗位的匹配情况</h2>
          <p>{result.summary}</p>
        </div>
      </section>

      <div className="insight-grid">
        <InsightList title="匹配优势" items={result.strengths} tone="positive" />
        <InsightList title="能力差距" items={result.gaps} tone="warning" />
      </div>
      <InsightList title="简历改进建议" items={result.resume_suggestions} tone="neutral" />

      <section className="questions-section">
        <div className="section-heading">
          <div>
            <p className="section-label">个性化准备</p>
            <h2>面试问题</h2>
          </div>
          <span>共 {result.interview_questions.length} 题</span>
        </div>
        <div className="question-list">
          {result.interview_questions.map((item, index) => (
            <article className="question-item" key={`${index}-${item.question}`}>
              <div className="question-number">{String(index + 1).padStart(2, "0")}</div>
              <div>
                <h3>{item.question}</h3>
                <p className="question-purpose">
                  <Target size={15} aria-hidden />
                  {item.purpose}
                </p>
                <ul>
                  {item.answer_points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </div>
            </article>
          ))}
        </div>
      </section>

      <InterviewPractice analysis={analysis} />

      <footer className="result-meta">
        模型：{analysis.model_name} · 耗时 {(analysis.duration_ms / 1000).toFixed(1)} 秒
        {analysis.total_tokens ? ` · ${analysis.total_tokens} tokens` : ""}
      </footer>
    </div>
  );
}
