from evaluation.run_evaluation import render_markdown, summarize_report


def test_evaluation_summary_and_markdown():
    report = {
        "generated_at": "2026-06-15T00:00:00+00:00",
        "models": {"llm": "test-llm", "embedding": "test-embedding"},
        "analysis_results": [
            {
                "case_id": "analysis",
                "succeeded": True,
                "duration_ms": 100,
                "total_tokens": 50,
            }
        ],
        "interview_results": [
            {
                "case_id": "pair",
                "succeeded": True,
                "score_gap": 25,
                "weak_duration_ms": 80,
                "strong_duration_ms": 120,
                "weak_total_tokens": 30,
                "strong_total_tokens": 40,
            }
        ],
        "retrieval_results": [
            {"case_id": "rag", "succeeded": True, "hit": True}
        ],
    }

    report["summary"] = summarize_report(report)
    markdown = render_markdown(report)

    assert report["summary"]["structured_output_success_rate"] == 1
    assert report["summary"]["strong_answer_win_rate"] == 1
    assert report["summary"]["average_strong_weak_score_gap"] == 25
    assert report["summary"]["rag_recall_at_k"] == 1
    assert "Structured output success: 100.0%" in markdown
    assert "source resume text" in markdown
