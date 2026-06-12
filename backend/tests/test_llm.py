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


class FakeCompletions:
    def __init__(self, contents):
        self.contents = iter(contents)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
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

    with pytest.raises(LLMServiceError, match="连续两次"):
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
async def test_two_invalid_feedback_outputs_fail():
    service = LLMService(Settings(deepseek_api_key="test"))
    service.client.chat.completions = FakeCompletions(["{}", "{}"])

    with pytest.raises(LLMServiceError, match="无效评分结构"):
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
            "无法连接",
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
