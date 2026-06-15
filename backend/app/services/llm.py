import json
import logging
import time
from dataclasses import dataclass

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI
from pydantic import ValidationError

from app.config import Settings
from app.schemas import (
    AnalysisResult,
    InterviewFeedback,
    InterviewQuestion,
    KnowledgeReference,
)

ANALYSIS_PROMPT_VERSION = "analysis-v2"
INTERVIEW_PROMPT_VERSION = "interview-v3"
logger = logging.getLogger(__name__)


class LLMServiceError(RuntimeError):
    """将第三方模型异常转换为应用内部的统一错误。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LLMAnalysis:
    result: AnalysisResult
    model_name: str
    duration_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    prompt_version: str = ANALYSIS_PROMPT_VERSION


@dataclass
class LLMInterviewEvaluation:
    feedback: InterviewFeedback
    model_name: str
    duration_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    prompt_version: str = INTERVIEW_PROMPT_VERSION


SYSTEM_PROMPT = """你是一名严谨的中文技术招聘顾问。
请根据候选人简历和职位描述，给出客观、可追溯的匹配分析。
不要虚构简历中不存在的经历。只返回 JSON，不要使用 Markdown 代码块。
必须生成恰好 8 道个性化面试题。
返回结构：
{
  "match_score": 0到100的整数,
  "summary": "总体结论",
  "strengths": ["优势"],
  "gaps": ["差距"],
  "resume_suggestions": ["简历建议"],
  "interview_questions": [
    {"question": "问题", "purpose": "考察目标", "answer_points": ["回答要点1", "回答要点2"]}
  ]
}"""

INTERVIEW_FEEDBACK_PROMPT = """你是一名严格但有建设性的中文技术面试官。
请结合候选人简历、目标岗位、面试题、考察目的和参考要点，评价候选人的实际回答。
不要因为回答篇幅长而提高分数，也不要虚构回答中不存在的内容。
strengths 必须包含至少一项。即使回答很弱，也要指出一项真实、有限的优点，例如回应了题目方向；不得为了填充字段而拔高评价。
只返回 JSON，不要使用 Markdown 代码块。
返回结构：
{
  "score": 0到100的整数,
  "summary": "总体评价",
  "strengths": ["回答优点"],
  "improvements": ["不足与改进建议"],
  "suggested_answer_points": ["更好的回答要点1", "更好的回答要点2"]
}"""


class LLMService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key or "missing-key",
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
        )

    async def analyze(self, resume_text: str, job_description: str) -> LLMAnalysis:
        if not self.settings.deepseek_api_key:
            raise LLMServiceError(
                "llm_not_configured",
                "AI 服务尚未配置，请联系管理员",
            )

        user_prompt = f"候选人简历：\n{resume_text}\n\n职位描述：\n{job_description}"
        started_at = time.perf_counter()
        last_error: Exception | None = None

        # 模型偶尔会返回不完整 JSON，因此校验失败后携带反馈重试一次。
        for attempt in range(2):
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            if attempt == 1:
                messages.append(
                    {
                        "role": "user",
                        "content": "上一次结果未通过结构校验。请严格按指定 JSON 结构重新完整输出。",
                    }
                )

            try:
                response = await self.client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                content = response.choices[0].message.content or ""
                result = AnalysisResult.model_validate(json.loads(content))
                usage = response.usage
                return LLMAnalysis(
                    result=result,
                    model_name=response.model or self.settings.llm_model,
                    duration_ms=round((time.perf_counter() - started_at) * 1000),
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                    prompt_version=ANALYSIS_PROMPT_VERSION,
                )
            except (json.JSONDecodeError, ValidationError, IndexError) as exc:
                last_error = exc
            except APITimeoutError as exc:
                raise LLMServiceError(
                    "llm_timeout",
                    "AI 服务响应超时，请稍后重试",
                ) from exc
            except APIConnectionError as exc:
                raise LLMServiceError(
                    "llm_unavailable",
                    "AI 服务暂时不可用，请稍后重试",
                ) from exc
            except Exception as exc:
                logger.exception("Unexpected LLM analysis failure")
                raise LLMServiceError(
                    "llm_provider_error",
                    "AI 服务调用失败，请稍后重试",
                ) from exc

        raise LLMServiceError(
            "llm_invalid_output",
            "AI 服务连续返回了无效结果，请稍后重试",
        ) from last_error

    async def evaluate_interview_answer(
        self,
        resume_text: str,
        job_description: str,
        question: InterviewQuestion,
        answer_text: str,
        references: list[KnowledgeReference] | None = None,
    ) -> LLMInterviewEvaluation:
        """评价单道面试回答，并保证模型输出符合固定结构。"""
        if not self.settings.deepseek_api_key:
            raise LLMServiceError(
                "llm_not_configured",
                "AI 服务尚未配置，请联系管理员",
            )

        reference_context = ""
        if references:
            formatted = "\n\n".join(
                f"资料《{item.title}》（相关度 {item.similarity:.2f}）：\n{item.content}"
                for item in references
            )
            reference_context = (
                "\n\n以下是从用户知识库检索到的参考资料。"
                "请优先依据资料评价；资料未覆盖的部分再结合题目参考要点。"
                "不得虚构资料中不存在的公司要求：\n"
                f"{formatted}"
            )

        user_prompt = (
            f"候选人简历：\n{resume_text}\n\n"
            f"目标岗位：\n{job_description}\n\n"
            f"面试题：{question.question}\n"
            f"考察目的：{question.purpose}\n"
            f"参考要点：{'；'.join(question.answer_points)}\n\n"
            f"候选人回答：\n{answer_text}"
            f"{reference_context}"
        )
        started_at = time.perf_counter()
        last_error: Exception | None = None

        for attempt in range(2):
            messages = [
                {"role": "system", "content": INTERVIEW_FEEDBACK_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            if attempt == 1:
                messages.append(
                    {
                        "role": "user",
                        "content": "上一次结果未通过结构校验。请严格按指定 JSON 结构重新完整输出。",
                    }
                )

            try:
                response = await self.client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                content = response.choices[0].message.content or ""
                feedback = InterviewFeedback.model_validate_json(content)
                usage = response.usage
                return LLMInterviewEvaluation(
                    feedback=feedback,
                    model_name=response.model or self.settings.llm_model,
                    duration_ms=round((time.perf_counter() - started_at) * 1000),
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                    prompt_version=INTERVIEW_PROMPT_VERSION,
                )
            except (json.JSONDecodeError, ValidationError, IndexError) as exc:
                last_error = exc
            except APITimeoutError as exc:
                raise LLMServiceError(
                    "llm_timeout",
                    "AI 服务响应超时，请稍后重试",
                ) from exc
            except APIConnectionError as exc:
                raise LLMServiceError(
                    "llm_unavailable",
                    "AI 服务暂时不可用，请稍后重试",
                ) from exc
            except Exception as exc:
                logger.exception("Unexpected LLM interview evaluation failure")
                raise LLMServiceError(
                    "llm_provider_error",
                    "AI 服务调用失败，请稍后重试",
                ) from exc

        raise LLMServiceError(
            "llm_invalid_output",
            "AI 服务连续返回了无效评分结果，请稍后重试",
        ) from last_error
