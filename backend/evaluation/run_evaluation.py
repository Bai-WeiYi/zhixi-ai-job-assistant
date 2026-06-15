"""Run a small, reproducible evaluation against the configured AI providers."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from app.config import get_settings
from app.schemas import InterviewQuestion
from app.services.knowledge import cosine_similarity
from app.services.llm import LLMService
from app.services.knowledge import EmbeddingService


DEFAULT_CASES = Path(__file__).with_name("cases.json")
DEFAULT_REPORT_DIR = Path(__file__).with_name("reports")


def load_cases(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_report(report: dict[str, Any]) -> dict[str, Any]:
    analyses = report["analysis_results"]
    pairs = report["interview_results"]
    retrieval = report["retrieval_results"]
    successful_analyses = [item for item in analyses if item["succeeded"]]
    successful_pairs = [item for item in pairs if item["succeeded"]]
    successful_retrieval = [item for item in retrieval if item["succeeded"]]
    gaps = [item["score_gap"] for item in successful_pairs]
    latencies = [
        item["duration_ms"]
        for item in successful_analyses
    ] + [
        item["strong_duration_ms"] + item["weak_duration_ms"]
        for item in successful_pairs
    ]
    tokens = [
        item["total_tokens"] or 0
        for item in successful_analyses
    ] + [
        (item["strong_total_tokens"] or 0) + (item["weak_total_tokens"] or 0)
        for item in successful_pairs
    ]
    return {
        "structured_output_success_rate": (
            (len(successful_analyses) + len(successful_pairs) * 2)
            / max(len(analyses) + len(pairs) * 2, 1)
        ),
        "strong_answer_win_rate": (
            sum(item["score_gap"] > 0 for item in successful_pairs)
            / max(len(successful_pairs), 1)
        ),
        "average_strong_weak_score_gap": mean(gaps) if gaps else None,
        "rag_recall_at_k": (
            sum(item["hit"] for item in successful_retrieval)
            / max(len(successful_retrieval), 1)
        ),
        "average_llm_latency_ms": mean(latencies) if latencies else None,
        "total_llm_tokens": sum(tokens),
    }


async def run_evaluation(cases: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    llm = LLMService(settings)
    embeddings = EmbeddingService(settings)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": {
            "llm": settings.llm_model,
            "embedding": settings.embedding_model,
        },
        "analysis_results": [],
        "interview_results": [],
        "retrieval_results": [],
    }

    for case in cases["analysis_cases"]:
        try:
            result = await llm.analyze(case["resume"], case["job_description"])
            report["analysis_results"].append(
                {
                    "case_id": case["id"],
                    "succeeded": True,
                    "match_score": result.result.match_score,
                    "duration_ms": result.duration_ms,
                    "total_tokens": result.total_tokens,
                    "prompt_version": result.prompt_version,
                }
            )
        except Exception as exc:
            report["analysis_results"].append(
                {
                    "case_id": case["id"],
                    "succeeded": False,
                    "error_type": type(exc).__name__,
                }
            )

    for case in cases["interview_pairs"]:
        question = InterviewQuestion.model_validate(case["question"])
        try:
            weak = await llm.evaluate_interview_answer(
                case["resume"],
                case["job_description"],
                question,
                case["weak_answer"],
            )
            strong = await llm.evaluate_interview_answer(
                case["resume"],
                case["job_description"],
                question,
                case["strong_answer"],
            )
            report["interview_results"].append(
                {
                    "case_id": case["id"],
                    "succeeded": True,
                    "weak_score": weak.feedback.score,
                    "strong_score": strong.feedback.score,
                    "score_gap": strong.feedback.score - weak.feedback.score,
                    "weak_duration_ms": weak.duration_ms,
                    "strong_duration_ms": strong.duration_ms,
                    "weak_total_tokens": weak.total_tokens,
                    "strong_total_tokens": strong.total_tokens,
                    "prompt_version": strong.prompt_version,
                }
            )
        except Exception as exc:
            report["interview_results"].append(
                {
                    "case_id": case["id"],
                    "succeeded": False,
                    "error_type": type(exc).__name__,
                }
            )

    documents = cases["knowledge_documents"]
    try:
        document_vectors = await embeddings.embed(
            [document["content"] for document in documents]
        )
        for case in cases["retrieval_cases"]:
            query_vector = (await embeddings.embed([case["query"]]))[0]
            ranked = sorted(
                (
                    {
                        "title": document["title"],
                        "similarity": cosine_similarity(vector, query_vector),
                    }
                    for document, vector in zip(
                        documents,
                        document_vectors,
                        strict=True,
                    )
                ),
                key=lambda item: item["similarity"],
                reverse=True,
            )[: settings.knowledge_top_k]
            report["retrieval_results"].append(
                {
                    "case_id": case["id"],
                    "succeeded": True,
                    "expected_document": case["expected_document"],
                    "retrieved_documents": [item["title"] for item in ranked],
                    "hit": any(
                        item["title"] == case["expected_document"] for item in ranked
                    ),
                }
            )
    except Exception as exc:
        for case in cases["retrieval_cases"]:
            report["retrieval_results"].append(
                {
                    "case_id": case["id"],
                    "succeeded": False,
                    "error_type": type(exc).__name__,
                }
            )

    report["summary"] = summarize_report(report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]

    def percent(value: float) -> str:
        return f"{value * 100:.1f}%"

    gap = summary["average_strong_weak_score_gap"]
    latency = summary["average_llm_latency_ms"]
    lines = [
        "# AI Evaluation Report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- LLM: `{report['models']['llm']}`",
        f"- Embedding: `{report['models']['embedding']}`",
        f"- Structured output success: {percent(summary['structured_output_success_rate'])}",
        f"- Strong-answer win rate: {percent(summary['strong_answer_win_rate'])}",
        f"- Average strong/weak score gap: {gap:.1f}" if gap is not None else "- Average strong/weak score gap: n/a",
        f"- RAG Recall@K: {percent(summary['rag_recall_at_k'])}",
        f"- Average LLM latency: {latency:.0f} ms" if latency is not None else "- Average LLM latency: n/a",
        f"- Total LLM tokens: {summary['total_llm_tokens']}",
        "",
        "This report contains aggregate metrics and case identifiers only. It excludes API keys and source resume text.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "latest.json"
    markdown_path = output_dir / "latest.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(run_evaluation(load_cases(args.cases)))
    json_path, markdown_path = write_reports(report, args.output_dir)
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")


if __name__ == "__main__":
    main()
