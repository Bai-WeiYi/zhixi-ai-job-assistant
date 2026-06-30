from app.schemas import (
    AdaptiveInterviewEvaluation,
    AdaptiveInterviewReport,
    AnalysisResult,
    InterviewFeedback,
    InterviewQuestion,
)
from app.services.llm import (
    LLMAdaptiveEvaluation,
    LLMAdaptiveReport,
    LLMAnalysis,
    LLMServiceError,
)


def sample_result() -> AnalysisResult:
    return AnalysisResult(
        match_score=82,
        summary="候选人的 Python 基础与岗位方向匹配，但工程经验仍需补充。",
        strengths=["具备 Python 基础"],
        gaps=["缺少生产部署经验"],
        resume_suggestions=["补充项目结果"],
        interview_questions=[
            InterviewQuestion(
                question=f"请说明第 {index} 个项目技术决策及其权衡。",
                purpose="考察工程判断",
                answer_points=["说明背景", "解释取舍"],
            )
            for index in range(1, 9)
        ],
    )


class FakeAdaptiveLLM:
    def __init__(self, scores: list[int]):
        self.scores = iter(scores)
        self.evaluation_calls = 0

    async def analyze(self, resume_text: str, job_description: str) -> LLMAnalysis:
        return LLMAnalysis(sample_result(), "test-model", 50, 10, 20, 30)

    async def evaluate_adaptive_answer(self, *args, **kwargs) -> LLMAdaptiveEvaluation:
        score = next(self.scores)
        self.evaluation_calls += 1
        follow_up = None
        if score < kwargs.get("follow_up_threshold", args[4] if len(args) > 4 else 60):
            follow_up = InterviewQuestion(
                question="你提到了技术选型，请具体说明失败方案和最终权衡。",
                purpose="针对薄弱点继续追问",
                answer_points=["失败方案", "选择依据"],
            )
        return LLMAdaptiveEvaluation(
            result=AdaptiveInterviewEvaluation(
                feedback=InterviewFeedback(
                    score=score,
                    summary="回答覆盖了问题方向，但工程细节仍可继续补充。",
                    strengths=["回应了题目方向"],
                    improvements=["补充方案比较与量化结果"],
                    suggested_answer_points=["背景", "方案", "结果"],
                ),
                follow_up_question=follow_up,
            ),
            model_name="test-model",
            duration_ms=80,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

    async def generate_adaptive_report(self, *args, **kwargs) -> LLMAdaptiveReport:
        return LLMAdaptiveReport(
            report=AdaptiveInterviewReport(
                overall_score=76,
                summary="五轮回答能够覆盖核心问题，但量化结果和异常处理仍需加强。",
                strengths=["表达结构清晰"],
                improvements=["工程细节不足"],
                action_plan=["补充项目指标", "练习异常处理案例"],
            ),
            model_name="test-model",
            duration_ms=100,
            prompt_tokens=20,
            completion_tokens=30,
            total_tokens=50,
        )


class FailOnceAdaptiveLLM(FakeAdaptiveLLM):
    def __init__(self):
        super().__init__([75])
        self.failed = False

    async def evaluate_adaptive_answer(self, *args, **kwargs):
        if not self.failed:
            self.failed = True
            raise LLMServiceError("llm_timeout", "AI 服务响应超时，请稍后重试")
        return await super().evaluate_adaptive_answer(*args, **kwargs)

def valid_analysis_payload():
    return {
        "resume_text": "我是一名 Python 开发者，学习过 FastAPI、SQL 和大模型 API，希望从事 AI 应用开发。",
        "job_description": "负责使用 Python 开发 AI 应用，要求掌握 FastAPI、数据库、模型调用和基础前端能力。",
    }


def create_analysis(client, llm: FakeAdaptiveLLM) -> int:
    client.app.state.llm_service = llm
    response = client.post("/api/analyses", json=valid_analysis_payload())
    assert response.status_code == 201
    return response.json()["id"]


def answer_current(client, session: dict, text: str = "我会结合项目背景说明技术方案、具体取舍以及最终交付结果和复盘。"):
    turn_id = session["current_question"]["turn_id"]
    return client.patch(
        f"/api/adaptive-interviews/{session['id']}/turns/{turn_id}",
        json={"answer_text": text},
    )


def test_low_score_routes_to_one_follow_up_then_next_main(client):
    llm = FakeAdaptiveLLM([59, 40])
    analysis_id = create_analysis(client, llm)
    started = client.post(f"/api/analyses/{analysis_id}/adaptive-interviews")

    assert started.status_code == 201
    session = started.json()
    assert session["current_question"]["source"] == "main"

    first = answer_current(client, session)
    assert first.status_code == 200
    session = first.json()
    assert session["current_question"]["source"] == "follow_up"
    assert session["turns"][0]["route_decision"] == "follow_up"

    second = answer_current(client, session)
    assert second.status_code == 200
    session = second.json()
    assert session["current_question"]["source"] == "main"
    assert session["current_question"]["source_question_number"] == 2
    assert session["turns"][1]["route_decision"] == "next_main"
    assert any(item["node"] == "prepare_follow_up" for item in session["execution_path"])


def test_score_at_threshold_moves_to_next_main_and_duplicate_is_idempotent(client):
    llm = FakeAdaptiveLLM([60])
    analysis_id = create_analysis(client, llm)
    session = client.post(f"/api/analyses/{analysis_id}/adaptive-interviews").json()
    turn_id = session["current_question"]["turn_id"]
    answer = "我会结合项目背景说明技术方案、具体取舍以及最终交付结果和复盘。"

    first = client.patch(
        f"/api/adaptive-interviews/{session['id']}/turns/{turn_id}",
        json={"answer_text": answer},
    )
    duplicate = client.patch(
        f"/api/adaptive-interviews/{session['id']}/turns/{turn_id}",
        json={"answer_text": answer},
    )
    changed = client.patch(
        f"/api/adaptive-interviews/{session['id']}/turns/{turn_id}",
        json={"answer_text": answer + "这次尝试修改已经提交的回答。"},
    )

    assert first.status_code == 200
    assert first.json()["current_question"]["source_question_number"] == 2
    assert duplicate.status_code == 200
    assert llm.evaluation_calls == 1
    assert changed.status_code == 409


def test_five_rounds_finish_with_report_and_can_be_reloaded(client):
    llm = FakeAdaptiveLLM([80, 81, 82, 83, 84])
    analysis_id = create_analysis(client, llm)
    session = client.post(f"/api/analyses/{analysis_id}/adaptive-interviews").json()

    for _ in range(5):
        response = answer_current(client, session)
        assert response.status_code == 200
        session = response.json()

    assert session["status"] == "completed"
    assert session["completed_turns"] == 5
    assert session["current_question"] is None
    assert session["report"]["overall_score"] == 76
    assert session["workflow_version"] == "adaptive-interview-v1"
    assert session["total_tokens"] == 200
    assert session["execution_path"][-1]["node"] == "generate_report"

    reloaded = client.get(f"/api/adaptive-interviews/{session['id']}")
    listed = client.get(f"/api/analyses/{analysis_id}/adaptive-interviews")
    assert reloaded.status_code == 200
    assert reloaded.json()["report"]["overall_score"] == 76
    assert listed.json()[0]["status"] == "completed"


def test_failed_evaluation_resumes_from_checkpoint_without_losing_answer(client):
    llm = FailOnceAdaptiveLLM()
    analysis_id = create_analysis(client, llm)
    session = client.post(f"/api/analyses/{analysis_id}/adaptive-interviews").json()
    turn_id = session["current_question"]["turn_id"]
    answer = "我会结合项目背景说明技术方案、具体取舍以及最终交付结果和复盘。"

    failed = client.patch(
        f"/api/adaptive-interviews/{session['id']}/turns/{turn_id}",
        json={"answer_text": answer},
    )
    retried = client.patch(
        f"/api/adaptive-interviews/{session['id']}/turns/{turn_id}",
        json={"answer_text": answer},
    )

    assert failed.status_code == 502
    assert failed.json()["detail"]["code"] == "llm_timeout"
    assert retried.status_code == 200
    assert retried.json()["completed_turns"] == 1
    assert retried.json()["turns"][0]["answer_text"] == answer
