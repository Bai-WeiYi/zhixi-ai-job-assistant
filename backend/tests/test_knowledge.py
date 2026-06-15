import json

import pytest
from sqlalchemy import create_engine, select

from app.config import get_settings
from app.models import InterviewAttempt, KnowledgeChunk, KnowledgeDocument
from app.schemas import AnalysisResult, InterviewFeedback
from app.services.knowledge import (
    KnowledgeServiceError,
    chunk_text,
    retrieve_references,
    validate_embedding_dimensions,
)
from app.services.llm import LLMAnalysis, LLMInterviewEvaluation


def unit_vector(index: int, dimensions: int = 1024) -> list[float]:
    vector = [0.0] * dimensions
    vector[index] = 1.0
    return vector


class FakeEmbedding:
    def __init__(self, vector: list[float] | None = None):
        self.vector = vector or unit_vector(0)

    async def embed(self, inputs: list[str]) -> list[list[float]]:
        return [self.vector.copy() for _ in inputs]


class FailingEmbedding:
    async def embed(self, inputs: list[str]) -> list[list[float]]:
        raise KnowledgeServiceError(
            "向量服务响应超时，请稍后重试",
            "embedding_timeout",
        )


class FakeLLM:
    async def analyze(self, resume_text: str, job_description: str) -> LLMAnalysis:
        result = AnalysisResult(
            match_score=82,
            summary="候选人的技术方向与岗位要求较为匹配，可以继续补充工程实践。",
            strengths=["具备 Python 和 FastAPI 基础"],
            gaps=["需要补充量化结果"],
            resume_suggestions=["说明项目中的技术取舍"],
            interview_questions=[
                {
                    "question": f"请说明第 {index} 个项目中的技术取舍和实现结果。",
                    "purpose": "考察工程判断",
                    "answer_points": ["说明背景", "解释取舍"],
                }
                for index in range(1, 9)
            ],
        )
        return LLMAnalysis(result, "test-model", 100, 10, 20, 30)

    async def evaluate_interview_answer(
        self,
        resume_text,
        job_description,
        question,
        answer_text,
        references=None,
    ) -> LLMInterviewEvaluation:
        return LLMInterviewEvaluation(
            feedback=InterviewFeedback(
                score=86,
                summary="回答结构清楚，并且能够结合资料说明关键技术选择。",
                strengths=["覆盖关键背景"],
                improvements=["补充量化指标"],
                suggested_answer_points=["背景与目标", "技术取舍"],
            ),
            model_name="test-model",
            duration_ms=80,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )


def valid_payload():
    return {
        "resume_text": "我是一名 Python 开发者，熟悉 FastAPI、SQLAlchemy 和大模型应用开发。",
        "job_description": "负责开发 AI 应用，要求掌握 Python、FastAPI、数据库、模型 API 和前端联调。",
    }


def test_chunk_text_prefers_paragraphs_and_splits_long_content():
    content = ("第一段资料。" * 40) + "\n\n" + ("第二段较长资料。" * 120)
    chunks = chunk_text(content)

    assert len(chunks) >= 2
    assert all(20 <= len(item) <= 700 for item in chunks)


def test_create_list_delete_text_document(client, db_session):
    client.app.state.embedding_service = FakeEmbedding()
    created = client.post(
        "/api/knowledge/documents",
        data={
            "title": "FastAPI 面试规范",
            "text": "FastAPI 使用 Depends 实现依赖注入，可用于数据库会话、鉴权和公共参数复用。" * 5,
        },
    )

    assert created.status_code == 201
    assert created.json()["source_type"] == "text"
    assert created.json()["chunk_count"] >= 1
    document_id = created.json()["id"]
    assert client.get("/api/knowledge/documents").json()[0]["id"] == document_id
    assert db_session.scalars(select(KnowledgeChunk)).all()

    assert client.delete(f"/api/knowledge/documents/{document_id}").status_code == 204
    assert db_session.scalars(select(KnowledgeDocument)).all() == []
    assert db_session.scalars(select(KnowledgeChunk)).all() == []


def test_document_input_validation_and_embedding_failure(client, db_session):
    both = client.post(
        "/api/knowledge/documents",
        data={"title": "错误资料", "text": "这是一段足够长的知识资料内容。" * 3},
        files={"file": ("guide.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert both.status_code == 422

    client.app.state.embedding_service = FailingEmbedding()
    failed = client.post(
        "/api/knowledge/documents",
        data={"title": "失败资料", "text": "这是一段用于测试向量服务失败回滚的知识资料。" * 4},
    )
    assert failed.status_code == 502
    assert failed.json()["detail"]["code"] == "embedding_timeout"
    assert db_session.scalars(select(KnowledgeDocument)).all() == []


def test_embedding_dimensions_are_validated_at_startup():
    engine = create_engine("sqlite://")
    validate_embedding_dimensions(
        get_settings().model_copy(update={"embedding_dimensions": 1024}),
        engine,
    )

    with pytest.raises(RuntimeError, match="must be 1024"):
        validate_embedding_dimensions(
            get_settings().model_copy(update={"embedding_dimensions": 768}),
            engine,
        )


def test_retrieval_filters_by_user(db_session):
    from app.models import User
    from app.services.auth import hash_password

    first = User(email="first-rag@example.com", password_hash=hash_password("password123"))
    second = User(email="second-rag@example.com", password_hash=hash_password("password123"))
    db_session.add_all([first, second])
    db_session.flush()
    first_doc = KnowledgeDocument(
        user_id=first.id,
        title="第一位用户资料",
        source_type="text",
        character_count=100,
        chunk_count=1,
    )
    second_doc = KnowledgeDocument(
        user_id=second.id,
        title="第二位用户资料",
        source_type="text",
        character_count=100,
        chunk_count=1,
    )
    db_session.add_all([first_doc, second_doc])
    db_session.flush()
    db_session.add_all(
        [
            KnowledgeChunk(
                document_id=first_doc.id,
                user_id=first.id,
                chunk_index=0,
                content="FastAPI 依赖注入资料",
                embedding=unit_vector(0),
            ),
            KnowledgeChunk(
                document_id=second_doc.id,
                user_id=second.id,
                chunk_index=0,
                content="不应被检索到的资料",
                embedding=unit_vector(0),
            ),
        ]
    )
    db_session.commit()

    references = retrieve_references(db_session, first.id, unit_vector(0), get_settings())
    assert [item.title for item in references] == ["第一位用户资料"]


def test_interview_saves_reference_snapshot(client, db_session):
    client.app.state.llm_service = FakeLLM()
    client.app.state.embedding_service = FakeEmbedding()
    document_response = client.post(
        "/api/knowledge/documents",
        data={"title": "评分标准", "text": "回答必须说明背景、技术取舍、执行过程和量化结果。" * 5},
    )
    assert document_response.status_code == 201

    analysis_id = client.post("/api/analyses", json=valid_payload()).json()["id"]
    response = client.post(
        f"/api/analyses/{analysis_id}/questions/1/attempts",
        json={"answer_text": "我会说明项目背景、技术方案的取舍、具体执行过程以及最终的量化结果。"},
    )

    assert response.status_code == 201
    assert response.json()["references"][0]["title"] == "评分标准"
    attempt = db_session.scalar(select(InterviewAttempt))
    assert json.loads(attempt.rag_context_json)[0]["title"] == "评分标准"

    client.delete(f"/api/knowledge/documents/{document_response.json()['id']}")
    history = client.get(f"/api/analyses/{analysis_id}/interview-attempts")
    assert history.json()[0]["references"][0]["title"] == "评分标准"
