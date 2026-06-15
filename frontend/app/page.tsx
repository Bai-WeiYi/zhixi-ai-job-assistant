"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { FileText, LoaderCircle, Sparkles, Upload } from "lucide-react";

import { AnalysisResultView } from "@/components/analysis-result";
import { createAnalysis, getUsage, parseResume } from "@/lib/api";
import type { AnalysisResponse, UsageSummary } from "@/lib/types";

const SAMPLE_RESUME =
  "我是一名 Python 开发者，掌握 Python 基础语法，学习过 FastAPI、SQL 和大模型 API。希望从事 AI 应用开发，并通过项目提升前后端工程能力。";
const SAMPLE_JD =
  "负责使用 Python 和 FastAPI 开发 AI 应用后端，完成大模型 API 接入、数据库设计和前端联调。要求理解 REST API、SQL、Git，并具备良好的问题分析能力。";

export default function HomePage() {
  const [resumeText, setResumeText] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isParsing, setIsParsing] = useState(false);
  const [error, setError] = useState("");
  const [parsedInfo, setParsedInfo] = useState("");
  const [success, setSuccess] = useState("");
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  function refreshUsage() {
    return getUsage()
      .then(setUsage)
      .catch(() => undefined);
  }

  useEffect(() => {
    void refreshUsage();
  }, []);

  async function handlePdf(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setError("");
    setParsedInfo("");
    setIsParsing(true);
    try {
      const parsed = await parseResume(file);
      setResumeText(parsed.text);
      setParsedInfo(`PDF 提取成功：${parsed.page_count} 页，共 ${parsed.character_count} 个字符`);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "PDF 解析失败");
    } finally {
      setIsParsing(false);
      event.target.value = "";
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setIsSubmitting(true);
    try {
      const result = await createAnalysis(resumeText, jobDescription);
      setAnalysis(result);
      setSuccess("分析已完成并保存，可以在历史记录中再次查看。");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "分析失败");
    } finally {
      setIsSubmitting(false);
      void refreshUsage();
    }
  }

  function fillSample() {
    setResumeText(SAMPLE_RESUME);
    setJobDescription(SAMPLE_JD);
    setError("");
    setParsedInfo("");
    setSuccess("");
  }

  return (
    <main className="workspace-shell">
      <section className="page-intro">
        <div>
          <h1>读懂岗位，也看清自己的下一步</h1>
          <p>输入简历和职位描述，获得匹配分析、改进建议与个性化面试题。</p>
        </div>
        <button className="text-button" onClick={fillSample} type="button">
          填入示例
        </button>
      </section>

      <div className="workspace-grid">
        <form className="input-panel" onSubmit={handleSubmit}>
          <div className="panel-heading">
            <div>
              <span>01</span>
              <h2>提供分析材料</h2>
            </div>
            <p>内容越具体，分析越准确</p>
          </div>

          <label className="field-label" htmlFor="resume">
            简历内容
            <span>{resumeText.length} 字</span>
          </label>
          <textarea
            id="resume"
            minLength={30}
            maxLength={30000}
            onChange={(event) => setResumeText(event.target.value)}
            placeholder="粘贴你的简历文本，或上传带文本层的 PDF..."
            required
            rows={11}
            value={resumeText}
          />
          <label className={`upload-button ${isParsing ? "disabled" : ""}`}>
            {isParsing ? <LoaderCircle className="spin" size={17} /> : <Upload size={17} />}
            {isParsing ? "正在提取 PDF..." : "上传 PDF 简历"}
            <input accept=".pdf,application/pdf" disabled={isParsing} onChange={handlePdf} type="file" />
          </label>
          {parsedInfo ? (
            <div className="success-message compact" role="status">
              {parsedInfo}
            </div>
          ) : null}

          <label className="field-label" htmlFor="job-description">
            职位描述
            <span>{jobDescription.length} 字</span>
          </label>
          <textarea
            id="job-description"
            minLength={30}
            maxLength={15000}
            onChange={(event) => setJobDescription(event.target.value)}
            placeholder="粘贴完整的岗位职责、技能要求和加分项..."
            required
            rows={9}
            value={jobDescription}
          />

          {error ? <div className="error-message">{error}</div> : null}
          {success ? (
            <div className="success-message" role="status">
              {success}
            </div>
          ) : null}
          <button className="primary-button" disabled={isSubmitting || isParsing} type="submit">
            {isSubmitting ? <LoaderCircle className="spin" size={19} /> : <Sparkles size={19} />}
            {isSubmitting ? "AI 正在分析..." : "开始分析"}
          </button>
          <div className="usage-note">
            <span>
              今日分析额度：
              {usage ? `剩余 ${usage.analysis.remaining}/${usage.analysis.limit} 次` : "读取中"}
            </span>
            {isSubmitting ? <small>免费后端首次唤醒可能需要约一分钟</small> : null}
          </div>
          <p className="privacy-note">
            简历和职位描述会发送至第三方 AI 服务进行分析，请先移除身份证号、电话、住址等敏感信息。
          </p>
        </form>

        <section className="result-panel" aria-live="polite">
          {analysis ? (
            <AnalysisResultView analysis={analysis} />
          ) : (
            <div className="empty-result">
              <div className="empty-icon">
                <FileText size={28} />
              </div>
              <h2>分析结果会显示在这里</h2>
              <p>提交后，你将看到岗位匹配度、能力差距、简历建议和 8 道面试题。</p>
              <ol>
                <li>填写或上传简历</li>
                <li>粘贴目标岗位 JD</li>
                <li>等待 AI 完成结构化分析</li>
              </ol>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
