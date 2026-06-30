import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError

from app.config import Settings
from app.schemas import InterviewQuestion
from app.services.llm import LLMService, LLMServiceError


def valid_model_json() -> str:
    return json.dumps(
        {
            "match_score": 75,
            "summary": "整体方向匹配，工程实践和项目深度仍有提升空间。",
            "strengths": ["Python 基础"],
            "gaps": ["缺少部署经验"],
            "resume_suggestions": ["补充量化结果"],
            "interview_questions": [
                {
                    "question": f"第 {index} 道面试题，请解释你的实现方案。",
                    "purpose": "考察技术理解",
                    "answer_points": ["问题背景", "方案权衡"],
                }
                for index in range(1, 9)
            ],
        },
        ensure_ascii=False,
    )


def valid_feedback_json() -> str:
    return json.dumps(
        {
            "score": 88,
            "summary": "回答覆盖了核心技术决策，也能说明实现过程和最终结果。",
            "strengths": ["结构清楚", "技术取舍具体"],
            "improvements": ["补充量化指标"],
            "suggested_answer_points": ["项目背景", "关键行动", "结果复盘"],
        },
        ensure_ascii=False,
    )


def valid_adaptive_json(score: int = 59) -> str:
    return json.dumps(
        {
            "feedback": json.loads(valid_feedback_json()) | {"score": score},
            "follow_up_question": (
                {
                    "question": "请具体说明一次失败方案以及你最终如何完成技术取舍。",
                    "purpose": "追问工程判断",
                    "answer_points": ["失败方案", "选择依据"],
                }
                if score < 60
                else None
            ),
        },
        ensure_ascii=False,
    )


def valid_adaptive_report_json() -> str:
    return json.dumps(
        {
            "overall_score": 78,
            "summary": "整体表达清晰，能够说明主要技术决策，但工程指标仍需补充。",
            "strengths": ["技术方向明确"],
            "improvements": ["量化结果不足"],
            "action_plan": ["补充性能指标", "练习故障排查案例"],
        },
        ensure_ascii=False,
    )


class FakeCompletions:
    def __init__(self, contents):
        self.contents = iter(contents)
        self.calls = 0
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        content = next(self.contents)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            model="fake-model",
        )


class ErrorCompletions:
    def __init__(self, error):
        self.error = error

    async def create(self, **kwargs):
        raise self.error


def sample_question() -> InterviewQuestion:
    return InterviewQuestion(
        question="请介绍项目中最重要的一次技术取舍。",
        purpose="考察工程判断",
        answer_points=["项目背景", "方案比较", "最终结果"],
    )


@pytest.mark.asyncio
async def test_invalid_output_retries_once():
    service = LLMService(Settings(deepseek_api_key="test"))
    completions = FakeCompletions(["not-json", valid_model_json()])
    service.client.chat.completions = completions

    result = await service.analyze("简历" * 30, "职位" * 30)
    assert result.result.match_score == 75
    assert completions.calls == 2


@pytest.mark.asyncio
async def test_two_invalid_outputs_fail():
    service = LLMService(Settings(deepseek_api_key="test"))
    service.client.chat.completions = FakeCompletions(["{}", "{}"])

    with pytest.raises(LLMServiceError, match="连续返回了无效结果"):
        await service.analyze("简历" * 30, "职位" * 30)


@pytest.mark.asyncio
async def test_invalid_feedback_retries_once():
    service = LLMService(Settings(deepseek_api_key="test"))
    completions = FakeCompletions(["not-json", valid_feedback_json()])
    service.client.chat.completions = completions

    result = await service.evaluate_interview_answer(
        "简历" * 30,
        "职位" * 30,
        sample_question(),
        "我比较了不同技术方案，并结合项目规模选择了 FastAPI，最终完成接口交付。",
    )
    assert result.feedback.score == 88
    assert completions.calls == 2


@pytest.mark.asyncio
async def test_feedback_prompt_includes_rag_references():
    from app.schemas import KnowledgeReference

    service = LLMService(Settings(deepseek_api_key="test"))
    completions = FakeCompletions([valid_feedback_json()])
    service.client.chat.completions = completions

    await service.evaluate_interview_answer(
        "简历" * 30,
        "职位" * 30,
        sample_question(),
        "我会说明背景、方案取舍和最终结果。",
        references=[
            KnowledgeReference(
                document_id=1,
                title="公司后端面试标准",
                content="回答必须说明安全性、异常处理和量化结果。",
                similarity=0.88,
            )
        ],
    )

    prompt = completions.last_kwargs["messages"][1]["content"]
    assert "公司后端面试标准" in prompt
    assert "不得虚构资料中不存在的公司要求" in prompt


@pytest.mark.asyncio
async def test_feedback_prompt_requires_a_truthful_strength():
    service = LLMService(Settings(deepseek_api_key="test"))
    completions = FakeCompletions([valid_feedback_json()])
    service.client.chat.completions = completions

    result = await service.evaluate_interview_answer(
        "简历" * 30,
        "职位" * 30,
        sample_question(),
        "我暂时没有完整经验，但会先说明自己的理解和排查思路。",
    )

    system_prompt = completions.last_kwargs["messages"][0]["content"]
    assert "strengths 必须包含至少一项" in system_prompt
    assert result.prompt_version == "interview-v3"


@pytest.mark.asyncio
async def test_two_invalid_feedback_outputs_fail():
    service = LLMService(Settings(deepseek_api_key="test"))
    service.client.chat.completions = FakeCompletions(["{}", "{}"])

    with pytest.raises(LLMServiceError, match="无效评分结果"):
        await service.evaluate_interview_answer(
            "简历" * 30,
            "职位" * 30,
            sample_question(),
            "我比较了不同技术方案，并结合项目规模选择了 FastAPI，最终完成接口交付。",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (APITimeoutError(httpx.Request("POST", "https://example.com")), "超时"),
        (
            APIConnectionError(
                message="connection failed",
                request=httpx.Request("POST", "https://example.com"),
            ),
            "暂时不可用",
        ),
    ],
)
async def test_feedback_api_errors_are_readable(error, message):
    service = LLMService(Settings(deepseek_api_key="test"))
    service.client.chat.completions = ErrorCompletions(error)

    with pytest.raises(LLMServiceError, match=message):
        await service.evaluate_interview_answer(
            "简历" * 30,
            "职位" * 30,
            sample_question(),
            "我比较了不同技术方案，并结合项目规模选择了 FastAPI，最终完成接口交付。",
        )


@pytest.mark.asyncio
async def test_provider_error_does_not_expose_original_message():
    service = LLMService(Settings(deepseek_api_key="test"))
    service.client.chat.completions = ErrorCompletions(
        RuntimeError("secret upstream response")
    )

    with pytest.raises(LLMServiceError) as raised:
        await service.analyze("简历" * 30, "职位" * 30)

    assert raised.value.code == "llm_provider_error"
    assert "secret upstream response" not in str(raised.value)


@pytest.mark.asyncio
async def test_adaptive_evaluation_enforces_score_follow_up_rule():
    service = LLMService(Settings(deepseek_api_key="test"))
    completions = FakeCompletions([valid_adaptive_json(59)])
    service.client.chat.completions = completions

    result = await service.evaluate_adaptive_answer(
        "简历" * 30,
        "职位" * 30,
        sample_question(),
        "我说明了技术方向，但还没有补充方案比较和量化结果。",
        60,
    )

    assert result.result.feedback.score == 59
    assert result.result.follow_up_question is not None
    assert result.prompt_version == "adaptive-evaluation-v1"


@pytest.mark.asyncio
async def test_adaptive_report_is_structured():
    service = LLMService(Settings(deepseek_api_key="test"))
    service.client.chat.completions = FakeCompletions([valid_adaptive_report_json()])

    result = await service.generate_adaptive_report(
        "简历" * 30,
        "职位" * 30,
        [{"round": 1, "question": "问题", "answer": "回答", "feedback": {"score": 78}}],
    )

    assert result.report.overall_score == 78
    assert result.prompt_version == "adaptive-report-v1"
