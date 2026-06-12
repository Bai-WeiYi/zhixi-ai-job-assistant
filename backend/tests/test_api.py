from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from app.config import get_settings
from app.demo_seed import (
    DEMO_MODEL_NAME,
    ensure_portfolio_user,
    seed_demo_data,
)
from app.models import AIUsageEvent, Analysis, InterviewAttempt, User
from app.schemas import AnalysisResult, InterviewFeedback
from app.services.llm import LLMAnalysis, LLMInterviewEvaluation, LLMServiceError


def sample_result() -> AnalysisResult:
    return AnalysisResult(
        match_score=82,
        summary="候选人的 Python 基础与岗位方向匹配，但工程经验仍需补充。",
        strengths=["具备 Python 基础", "有明确的 AI 应用方向"],
        gaps=["缺少生产环境部署经验"],
        resume_suggestions=["补充项目中的具体技术决策"],
        interview_questions=[
            {
                "question": f"请说明第 {index} 个项目技术决策及其权衡。",
                "purpose": "考察工程判断",
                "answer_points": ["说明背景", "解释取舍"],
            }
            for index in range(1, 9)
        ],
    )


class FakeLLM:
    async def analyze(self, resume_text: str, job_description: str) -> LLMAnalysis:
        return LLMAnalysis(sample_result(), "test-model", 120, 100, 200, 300)

    async def evaluate_interview_answer(
        self,
        resume_text,
        job_description,
        question,
        answer_text,
    ) -> LLMInterviewEvaluation:
        return LLMInterviewEvaluation(
            feedback=InterviewFeedback(
                score=86,
                summary="回答结构清楚，能够结合项目说明关键技术选择。",
                strengths=["说明了项目背景", "解释了技术取舍"],
                improvements=["补充量化结果"],
                suggested_answer_points=["背景与目标", "具体行动", "结果与复盘"],
            ),
            model_name="test-model",
            duration_ms=80,
            prompt_tokens=50,
            completion_tokens=60,
            total_tokens=110,
        )


class FailingLLM:
    async def analyze(self, resume_text: str, job_description: str):
        raise LLMServiceError("模型响应超时，请稍后重试")

    async def evaluate_interview_answer(self, *args):
        raise LLMServiceError("模型响应超时，请稍后重试")


def valid_payload():
    return {
        "resume_text": "我是一名 Python 开发者，学习过 FastAPI、SQL 和大模型 API，希望从事 AI 应用开发。",
        "job_description": "负责使用 Python 开发 AI 应用，要求掌握 FastAPI、数据库、模型调用和基础前端能力。",
    }


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_protected_api_requires_login(anonymous_client):
    response = anonymous_client.get("/api/analyses")
    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"


def test_register_login_and_me(anonymous_client):
    registered = anonymous_client.post(
        "/api/auth/register",
        json={"email": " User@Example.com ", "password": "password123"},
    )
    assert registered.status_code == 201
    assert registered.json()["user"]["email"] == "user@example.com"
    assert registered.json()["token_type"] == "bearer"

    duplicate = anonymous_client.post(
        "/api/auth/register",
        json={"email": "USER@example.com", "password": "password123"},
    )
    assert duplicate.status_code == 409

    failed = anonymous_client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )
    assert failed.status_code == 401
    assert failed.json()["detail"] == "邮箱或密码错误"

    logged_in = anonymous_client.post(
        "/api/auth/login",
        json={"email": "USER@example.com", "password": "password123"},
    )
    token = logged_in.json()["access_token"]
    me = anonymous_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logged_in.status_code == 200
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


def test_invalid_and_expired_tokens(anonymous_client):
    invalid = anonymous_client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    settings = get_settings()
    expired_token = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    expired = anonymous_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert invalid.status_code == 401
    assert expired.status_code == 401


def test_create_list_get_and_delete_analysis(client):
    client.app.state.llm_service = FakeLLM()

    created = client.post("/api/analyses", json=valid_payload())
    assert created.status_code == 201
    analysis_id = created.json()["id"]
    assert created.json()["result"]["match_score"] == 82

    listed = client.get("/api/analyses")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == analysis_id

    assert client.get(f"/api/analyses/{analysis_id}").status_code == 200
    assert client.delete(f"/api/analyses/{analysis_id}").status_code == 204
    assert client.get(f"/api/analyses/{analysis_id}").status_code == 404


def test_input_validation(client):
    response = client.post(
        "/api/analyses",
        json={"resume_text": "太短", "job_description": "也太短"},
    )
    assert response.status_code == 422


def test_model_error_is_readable(client):
    client.app.state.llm_service = FailingLLM()
    response = client.post("/api/analyses", json=valid_payload())
    assert response.status_code == 502
    assert "超时" in response.json()["detail"]


def test_failed_analysis_counts_toward_daily_limit(client, db_session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "user_daily_analysis_limit", 1)
    client.app.state.llm_service = FailingLLM()

    failed = client.post("/api/analyses", json=valid_payload())
    limited = client.post("/api/analyses", json=valid_payload())
    usage = client.get("/api/usage")

    assert failed.status_code == 502
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
    assert usage.json()["analysis"]["remaining"] == 0
    events = db_session.scalars(select(AIUsageEvent)).all()
    assert len(events) == 1
    assert events[0].status == "failed"


def test_invalid_analysis_id(client):
    assert client.get("/api/analyses/999").status_code == 404
    assert client.delete("/api/analyses/999").status_code == 404


def test_create_and_list_interview_attempts(client, db_session):
    client.app.state.llm_service = FakeLLM()
    analysis_id = client.post("/api/analyses", json=valid_payload()).json()["id"]
    answer = "我先分析岗位需要解决的问题，再说明 FastAPI 与 SQLAlchemy 的技术取舍和实现结果。"

    first = client.post(
        f"/api/analyses/{analysis_id}/questions/1/attempts",
        json={"answer_text": answer},
    )
    second = client.post(
        f"/api/analyses/{analysis_id}/questions/1/attempts",
        json={"answer_text": answer + "第二次回答会进一步补充项目指标。"},
    )

    assert first.status_code == 201
    assert first.json()["feedback"]["score"] == 86
    assert second.status_code == 201

    listed = client.get(f"/api/analyses/{analysis_id}/interview-attempts")
    assert listed.status_code == 200
    assert [item["question_number"] for item in listed.json()] == [1, 1]

    assert client.delete(f"/api/analyses/{analysis_id}").status_code == 204
    assert db_session.scalars(select(InterviewAttempt)).all() == []


def test_interview_attempt_validation(client):
    client.app.state.llm_service = FakeLLM()
    analysis_id = client.post("/api/analyses", json=valid_payload()).json()["id"]

    too_short = client.post(
        f"/api/analyses/{analysis_id}/questions/1/attempts",
        json={"answer_text": "太短"},
    )
    invalid_question = client.post(
        f"/api/analyses/{analysis_id}/questions/9/attempts",
        json={"answer_text": "这是一段超过二十个字符的有效面试回答内容，用于测试非法题号。"},
    )
    missing_analysis = client.post(
        "/api/analyses/999/questions/1/attempts",
        json={"answer_text": "这是一段超过二十个字符的有效面试回答内容，用于测试非法分析记录。"},
    )

    assert too_short.status_code == 422
    assert invalid_question.status_code == 422
    assert missing_analysis.status_code == 404
    assert client.get("/api/analyses/999/interview-attempts").status_code == 404


def test_interview_model_error_is_readable(client):
    client.app.state.llm_service = FakeLLM()
    analysis_id = client.post("/api/analyses", json=valid_payload()).json()["id"]
    client.app.state.llm_service = FailingLLM()

    response = client.post(
        f"/api/analyses/{analysis_id}/questions/1/attempts",
        json={"answer_text": "这是一段超过二十个字符的回答，用来验证模型超时错误能够正常返回。"},
    )
    assert response.status_code == 502
    assert "超时" in response.json()["detail"]


def test_invalid_pdf(client):
    response = client.post(
        "/api/resumes/parse",
        files={"file": ("resume.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert response.status_code == 400


def test_pdf_text_is_extracted(client, monkeypatch):
    class FakePage:
        def extract_text(self):
            return "Python 开发者，熟悉 FastAPI、SQLAlchemy 和大模型接口开发。" * 2

    class FakeReader:
        def __init__(self, stream):
            self.pages = [FakePage()]

    monkeypatch.setattr("app.services.pdf_parser.PdfReader", FakeReader)
    response = client.post(
        "/api/resumes/parse",
        files={"file": ("resume.pdf", b"%PDF-fake", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["page_count"] == 1
    assert "FastAPI" in response.json()["text"]


def test_demo_seed_is_idempotent_and_includes_attempts(db_session):
    first, first_created = seed_demo_data(db_session)
    second, second_created = seed_demo_data(db_session)

    assert first_created is True
    assert second_created is False
    assert first.id == second.id
    assert db_session.scalars(
        select(Analysis).where(Analysis.model_name == DEMO_MODEL_NAME)
    ).all() == [first]

    attempts = db_session.scalars(
        select(InterviewAttempt)
        .where(InterviewAttempt.analysis_id == first.id)
        .order_by(InterviewAttempt.id)
    ).all()
    assert [attempt.question_number for attempt in attempts] == [1, 1, 2, 4]


def test_portfolio_user_and_demo_are_idempotent(db_session):
    first_user, first_user_created = ensure_portfolio_user(
        db_session,
        "Portfolio@Example.com",
        "password123",
    )
    second_user, second_user_created = ensure_portfolio_user(
        db_session,
        "portfolio@example.com",
        "different-password",
    )
    first_analysis, first_analysis_created = seed_demo_data(
        db_session,
        owner_id=first_user.id,
    )
    second_analysis, second_analysis_created = seed_demo_data(
        db_session,
        owner_id=second_user.id,
    )

    assert first_user_created is True
    assert second_user_created is False
    assert first_user.id == second_user.id
    assert first_analysis_created is True
    assert second_analysis_created is False
    assert first_analysis.id == second_analysis.id
    assert first_analysis.user_id == first_user.id


def test_first_user_claims_legacy_analyses(anonymous_client, db_session):
    legacy = Analysis(
        resume_text=valid_payload()["resume_text"],
        job_description=valid_payload()["job_description"],
        result_json=sample_result().model_dump_json(),
        model_name="legacy-model",
        duration_ms=100,
    )
    db_session.add(legacy)
    db_session.commit()

    registered = anonymous_client.post(
        "/api/auth/register",
        json={"email": "first@example.com", "password": "password123"},
    )
    user_id = registered.json()["user"]["id"]
    db_session.refresh(legacy)
    assert legacy.user_id == user_id


def test_users_cannot_access_each_others_data(anonymous_client):
    anonymous_client.app.state.llm_service = FakeLLM()

    first = anonymous_client.post(
        "/api/auth/register",
        json={"email": "first@example.com", "password": "password123"},
    ).json()
    second = anonymous_client.post(
        "/api/auth/register",
        json={"email": "second@example.com", "password": "password123"},
    ).json()
    first_headers = {"Authorization": f"Bearer {first['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    analysis_id = anonymous_client.post(
        "/api/analyses",
        json=valid_payload(),
        headers=first_headers,
    ).json()["id"]

    assert anonymous_client.get(
        "/api/analyses",
        headers=second_headers,
    ).json() == []
    assert anonymous_client.get(
        f"/api/analyses/{analysis_id}",
        headers=second_headers,
    ).status_code == 404
    assert anonymous_client.get(
        f"/api/analyses/{analysis_id}/interview-attempts",
        headers=second_headers,
    ).status_code == 404
    assert anonymous_client.delete(
        f"/api/analyses/{analysis_id}",
        headers=second_headers,
    ).status_code == 404
    assert anonymous_client.post(
        f"/api/analyses/{analysis_id}/questions/1/attempts",
        json={"answer_text": "这是一段超过二十个字符的回答，用于验证不同用户之间无法访问数据。"},
        headers=second_headers,
    ).status_code == 404

    assert anonymous_client.get(
        f"/api/analyses/{analysis_id}",
        headers=first_headers,
    ).status_code == 200
