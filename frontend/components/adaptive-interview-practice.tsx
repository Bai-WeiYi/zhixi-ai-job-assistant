"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  GitBranch,
  LoaderCircle,
  Play,
  Send,
} from "lucide-react";

import {
  answerAdaptiveTurn,
  createAdaptiveInterview,
  getAdaptiveInterview,
  getUsage,
  listAdaptiveInterviews,
} from "@/lib/api";
import type {
  AdaptiveInterviewSession,
  AdaptiveTurn,
  AnalysisResponse,
  UsageSummary,
} from "@/lib/types";

type Props = { analysis: AnalysisResponse };

const routeLabels: Record<string, string> = {
  follow_up: "本轮低于 60 分，LangGraph 已进入针对性追问",
  next_main: "本轮达到切题条件，LangGraph 已切换下一道主问题",
  finish: "已完成 5 轮，LangGraph 正在汇总整场报告",
};

function LatestFeedback({ turn }: { turn: AdaptiveTurn }) {
  if (!turn.feedback) return null;
  return (
    <div className="adaptive-feedback">
      <div className="feedback-score">
        <strong>{turn.feedback.score}</strong>
        <span>本轮得分</span>
      </div>
      <div className="feedback-main">
        <h3>本轮反馈</h3>
        <p>{turn.feedback.summary}</p>
        {turn.route_decision ? (
          <div className="workflow-route">
            <GitBranch size={16} /> {routeLabels[turn.route_decision]}
          </div>
        ) : null}
        <div className="feedback-grid">
          <div className="feedback-positive">
            <h4><CheckCircle2 size={16} /> 回答优点</h4>
            <ul>{turn.feedback.strengths.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          <div className="feedback-warning">
            <h4><CircleAlert size={16} /> 改进方向</h4>
            <ul>{turn.feedback.improvements.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        </div>
        {turn.references.length > 0 ? (
          <div className="rag-references">
            <h4>本轮评分参考资料</h4>
            {turn.references.map((reference, index) => (
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
      </div>
    </div>
  );
}

export function AdaptiveInterviewPractice({ analysis }: Props) {
  const [session, setSession] = useState<AdaptiveInterviewSession | null>(null);
  const [answerText, setAnswerText] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([listAdaptiveInterviews(analysis.id), getUsage().catch(() => null)])
      .then(async ([records, quota]) => {
        if (!active) return;
        setUsage(quota);
        if (records.length > 0) {
          const detail = await getAdaptiveInterview(records[0].id);
          if (active) setSession(detail);
        }
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "自适应面试加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [analysis.id]);

  async function startInterview() {
    setError("");
    setSubmitting(true);
    try {
      setSession(await createAdaptiveInterview(analysis.id));
      setAnswerText("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "自适应面试创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitAnswer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session?.current_question) return;
    setError("");
    setSubmitting(true);
    try {
      const updated = await answerAdaptiveTurn(
        session.id,
        session.current_question.turn_id,
        answerText,
      );
      setSession(updated);
      setAnswerText("");
      void getUsage().then(setUsage).catch(() => undefined);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "回答提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <div className="center-state"><LoaderCircle className="spin" /> 正在恢复自适应面试...</div>;
  }

  if (!session) {
    return (
      <section className="adaptive-intro">
        <BrainCircuit size={32} />
        <div>
          <p className="section-label">LangGraph 自适应面试</p>
          <h2>让下一道题由你的回答决定</h2>
          <p>共 5 轮。系统从现有题库选择主问题，低于 60 分时针对薄弱点追问，否则切换新主题。</p>
          <button className="primary-button" disabled={submitting} onClick={startInterview} type="button">
            {submitting ? <LoaderCircle className="spin" size={18} /> : <Play size={18} />}
            {submitting ? "正在准备第一题..." : "开始自适应面试"}
          </button>
          {error ? <div className="error-message">{error}</div> : null}
        </div>
      </section>
    );
  }

  const answeredTurns = session.turns.filter((turn) => turn.feedback);
  const latestTurn = answeredTurns.at(-1);

  return (
    <section className="adaptive-session">
      <div className="adaptive-heading">
        <div>
          <p className="section-label">LangGraph 自适应面试</p>
          <h2>{session.status === "completed" ? "本场面试已完成" : "根据回答实时调整下一题"}</h2>
        </div>
        <div className="adaptive-progress">
          <strong>{session.completed_turns}/{session.max_rounds}</strong>
          <span>已完成轮次</span>
        </div>
      </div>
      <div className="progress-track" aria-label={`已完成 ${session.completed_turns} / ${session.max_rounds} 轮`}>
        <span style={{ width: `${(session.completed_turns / session.max_rounds) * 100}%` }} />
      </div>

      {session.current_question ? (
        <>
          <div className="adaptive-question">
            <div>
              <span>第 {session.current_question.round_number} 轮</span>
              <em>{session.current_question.source === "follow_up" ? "AI 针对性追问" : `主问题 ${session.current_question.source_question_number}`}</em>
            </div>
            <h3>{session.current_question.question}</h3>
            <p>{session.current_question.purpose}</p>
          </div>
          <form className="answer-form" onSubmit={submitAnswer}>
            <label className="field-label" htmlFor="adaptive-answer">
              你的回答 <span>{answerText.length}/5000 字</span>
            </label>
            <textarea
              id="adaptive-answer"
              maxLength={5000}
              minLength={20}
              onChange={(event) => setAnswerText(event.target.value)}
              placeholder="结合具体项目说明背景、行动、取舍、结果与复盘..."
              required
              rows={7}
              value={answerText}
            />
            {error ? <div className="error-message">{error}</div> : null}
            <button className="primary-button practice-submit" disabled={submitting} type="submit">
              {submitting ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}
              {submitting ? "LangGraph 正在评分并选择路径..." : "提交本轮回答"}
            </button>
            <div className="usage-note">
              <span>今日评分额度：{usage ? `剩余 ${usage.interview.remaining}/${usage.interview.limit} 次` : "读取中"}</span>
            </div>
          </form>
        </>
      ) : null}

      {latestTurn ? <LatestFeedback turn={latestTurn} /> : null}

      {session.report ? (
        <div className="adaptive-report">
          <div className="report-score"><strong>{session.report.overall_score}</strong><span>综合得分</span></div>
          <div>
            <h3>整场面试报告</h3>
            <p>{session.report.summary}</p>
            <div className="report-columns">
              <div><h4>稳定优势</h4><ul>{session.report.strengths.map((item) => <li key={item}>{item}</li>)}</ul></div>
              <div><h4>重点改进</h4><ul>{session.report.improvements.map((item) => <li key={item}>{item}</li>)}</ul></div>
              <div><h4>行动计划</h4><ol>{session.report.action_plan.map((item) => <li key={item}>{item}</li>)}</ol></div>
            </div>
            <button className="secondary-button" disabled={submitting} onClick={startInterview} type="button">再进行一场</button>
          </div>
        </div>
      ) : null}

      <details className="workflow-trace">
        <summary><GitBranch size={16} /> LangGraph 工作流详情</summary>
        <div className="workflow-meta">
          <span>版本 {session.workflow_version}</span>
          <span>当前节点 {session.current_node}</span>
          <span>Token {session.total_tokens}</span>
          <span>耗时 {(session.duration_ms / 1000).toFixed(1)} 秒</span>
        </div>
        <ol>
          {session.execution_path.map((event, index) => (
            <li key={`${event.node}-${index}`}>
              <strong>{event.node}</strong>
              <span>{event.detail}</span>
              <small>{event.duration_ms} ms</small>
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
