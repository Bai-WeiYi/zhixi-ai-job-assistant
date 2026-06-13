"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleAlert, LoaderCircle, RotateCcw, Send } from "lucide-react";

import { createInterviewAttempt, getUsage, listInterviewAttempts } from "@/lib/api";
import type { AnalysisResponse, InterviewAttempt, UsageSummary } from "@/lib/types";

type Props = {
  analysis: AnalysisResponse;
};

function FeedbackList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="feedback-list">
      <h4>{title}</h4>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function InterviewPractice({ analysis }: Props) {
  const [selectedQuestion, setSelectedQuestion] = useState(1);
  const [answerText, setAnswerText] = useState("");
  const [attempts, setAttempts] = useState<InterviewAttempt[]>([]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [success, setSuccess] = useState("");
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  function loadAttempts() {
    let active = true;
    setLoading(true);
    setLoadError("");

    const request = listInterviewAttempts(analysis.id)
      .then((records) => {
        if (active) setAttempts(records);
      })
      .catch((reason) => {
        if (active) {
          setLoadError(reason instanceof Error ? reason.message : "答题记录加载失败");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return { request, cancel: () => {
      active = false;
    } };
  }

  useEffect(() => {
    const loadingRequest = loadAttempts();
    void getUsage().then(setUsage).catch(() => undefined);
    return loadingRequest.cancel;
  }, [analysis.id]);

  const latestByQuestion = useMemo(() => {
    const latest = new Map<number, InterviewAttempt>();
    for (const attempt of attempts) {
      latest.set(attempt.question_number, attempt);
    }
    return latest;
  }, [attempts]);

  const answeredCount = latestByQuestion.size;
  const averageScore =
    answeredCount === 0
      ? null
      : Math.round(
          [...latestByQuestion.values()].reduce(
            (sum, attempt) => sum + attempt.feedback.score,
            0,
          ) / answeredCount,
        );
  const currentQuestion = analysis.result.interview_questions[selectedQuestion - 1];
  const currentAttempts = attempts.filter(
    (attempt) => attempt.question_number === selectedQuestion,
  );
  const latestAttempt = currentAttempts.at(-1);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setSubmitting(true);
    try {
      const previousScore = latestAttempt?.feedback.score;
      const attempt = await createInterviewAttempt(
        analysis.id,
        selectedQuestion,
        answerText,
      );
      setAttempts((current) => [...current, attempt]);
      setAnswerText("");
      setDrafts((current) => ({ ...current, [selectedQuestion]: "" }));
      const scoreDelta =
        previousScore === undefined ? null : attempt.feedback.score - previousScore;
      const change =
        scoreDelta === null
          ? ""
          : scoreDelta === 0
            ? "，与上次持平"
            : `，较上次${scoreDelta > 0 ? "提高" : "降低"} ${Math.abs(scoreDelta)} 分`;
      setSuccess(`评分完成：本次 ${attempt.feedback.score} 分${change}。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "回答评分失败");
    } finally {
      setSubmitting(false);
      void getUsage().then(setUsage).catch(() => undefined);
    }
  }

  return (
    <section className="practice-section">
      <div className="practice-heading">
        <div>
          <p className="section-label">模拟面试</p>
          <h2>逐题作答与 AI 评分</h2>
          <p>结合你的简历和目标岗位，练习后可以反复提交并比较进步。</p>
        </div>
        <div className="practice-stats">
          <span>已回答 {answeredCount}/8</span>
          <strong>{averageScore === null ? "--" : averageScore}</strong>
          <small>最新平均分</small>
        </div>
      </div>

      <div className="question-tabs" aria-label="选择面试题">
        {analysis.result.interview_questions.map((_, index) => {
          const number = index + 1;
          const latest = latestByQuestion.get(number);
          return (
            <button
              className={number === selectedQuestion ? "active" : ""}
              key={number}
              onClick={() => {
                setDrafts((current) => ({ ...current, [selectedQuestion]: answerText }));
                setSelectedQuestion(number);
                setAnswerText(drafts[number] ?? "");
                setError("");
                setSuccess("");
              }}
              type="button"
            >
              第 {number} 题
              {latest ? <span>{latest.feedback.score} 分</span> : null}
            </button>
          );
        })}
      </div>

      <div className="practice-question">
        <span>第 {selectedQuestion} 题</span>
        <h3>{currentQuestion.question}</h3>
        <p>{currentQuestion.purpose}</p>
      </div>

      <form className="answer-form" onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="interview-answer">
          你的回答
          <span>{answerText.length}/5000 字</span>
        </label>
        <textarea
          id="interview-answer"
          maxLength={5000}
          minLength={20}
          onChange={(event) => {
            setAnswerText(event.target.value);
            setDrafts((current) => ({
              ...current,
              [selectedQuestion]: event.target.value,
            }));
          }}
          placeholder="建议按背景、行动、结果和复盘的顺序组织回答，至少输入 20 个字..."
          required
          rows={7}
          value={answerText}
        />
        {error ? <div className="error-message">{error}</div> : null}
        {success ? (
          <div className="success-message" role="status">
            {success}
          </div>
        ) : null}
        <button className="primary-button practice-submit" disabled={submitting} type="submit">
          {submitting ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}
          {submitting ? "AI 正在评分..." : latestAttempt ? "再次提交练习" : "提交回答并评分"}
        </button>
        <div className="usage-note">
          <span>
            今日评分额度：
            {usage ? `剩余 ${usage.interview.remaining}/${usage.interview.limit} 次` : "读取中"}
          </span>
          {submitting ? <small>免费后端首次唤醒可能需要约一分钟</small> : null}
        </div>
      </form>

      {loading ? (
        <div className="practice-loading">
          <LoaderCircle className="spin" size={18} />
          正在读取练习记录...
        </div>
      ) : loadError && attempts.length === 0 ? (
        <div className="practice-empty state-column">
          <span>{loadError}</span>
          <button
            className="inline-action"
            onClick={() => void loadAttempts().request}
            type="button"
          >
            重新加载
          </button>
        </div>
      ) : latestAttempt ? (
        <div className="feedback-card">
          <div className="feedback-score">
            <strong>{latestAttempt.feedback.score}</strong>
            <span>本题最新得分</span>
          </div>
          <div className="feedback-main">
            <div className="feedback-title">
              <div>
                <h3>AI 反馈</h3>
                <p>{latestAttempt.feedback.summary}</p>
              </div>
              <span>已练习 {currentAttempts.length} 次</span>
            </div>
            <div className="feedback-grid">
              <div className="feedback-positive">
                <h4>
                  <CheckCircle2 size={16} /> 回答优点
                </h4>
                <ul>
                  {latestAttempt.feedback.strengths.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div className="feedback-warning">
                <h4>
                  <CircleAlert size={16} /> 改进方向
                </h4>
                <ul>
                  {latestAttempt.feedback.improvements.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
            <FeedbackList
              title="参考回答要点"
              items={latestAttempt.feedback.suggested_answer_points}
            />
            {(latestAttempt.references ?? []).length > 0 ? (
              <div className="rag-references">
                <h4>本次评分参考资料</h4>
                {(latestAttempt.references ?? []).map((reference, index) => (
                  <article key={`${reference.document_id}-${index}`}>
                    <div>
                      <strong>{reference.title}</strong>
                      <span>相关度 {Math.round(reference.similarity * 100)}%</span>
                    </div>
                    <p>{reference.content}</p>
                  </article>
                ))}
              </div>
            ) : null}
            {currentAttempts.length > 1 ? (
              <div className="attempt-history">
                <h4>
                  <RotateCcw size={15} /> 历次成绩
                </h4>
                <div>
                  {currentAttempts.map((attempt, index) => (
                    <span key={attempt.id}>
                      第 {index + 1} 次：{attempt.feedback.score} 分
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="practice-empty">这道题还没有练习记录，提交回答后会显示评分。</div>
      )}
    </section>
  );
}
