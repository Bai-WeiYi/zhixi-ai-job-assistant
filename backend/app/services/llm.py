import json
import time
from dataclasses import dataclass

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI
from pydantic import ValidationError

from app.config import Settings
from app.schemas import AnalysisResult, InterviewFeedback, InterviewQuestion


class LLMServiceError(RuntimeError):
    """将第三方模型异常转换为应用内部的统一错误。"""


@dataclass
class LLMAnalysis:
    result: AnalysisResult
    model_name: str
    duration_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


@dataclass
class LLMInterviewEvaluation:
    feedback: InterviewFeedback
    model_name: str
    duration_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


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
            raise LLMServiceError("尚未配置 DEEPSEEK_API_KEY")

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
                )
            except (json.JSONDecodeError, ValidationError, IndexError) as exc:
                last_error = exc
            except APITimeoutError as exc:
                raise LLMServiceError("模型响应超时，请稍后重试") from exc
            except APIConnectionError as exc:
                raise LLMServiceError("无法连接模型服务，请检查网络和接口地址") from exc
            except Exception as exc:
                raise LLMServiceError(f"模型调用失败：{exc}") from exc

        raise LLMServiceError("模型连续两次返回了无效结构") from last_error

    async def evaluate_interview_answer(
        self,
        resume_text: str,
        job_description: str,
        question: InterviewQuestion,
        answer_text: str,
    ) -> LLMInterviewEvaluation:
        """评价单道面试回答，并保证模型输出符合固定结构。"""
        if not self.settings.deepseek_api_key:
            raise LLMServiceError("尚未配置 DEEPSEEK_API_KEY")

        user_prompt = (
            f"候选人简历：\n{resume_text}\n\n"
            f"目标岗位：\n{job_description}\n\n"
            f"面试题：{question.question}\n"
            f"考察目的：{question.purpose}\n"
            f"参考要点：{'；'.join(question.answer_points)}\n\n"
            f"候选人回答：\n{answer_text}"
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
                )
            except (json.JSONDecodeError, ValidationError, IndexError) as exc:
                last_error = exc
            except APITimeoutError as exc:
                raise LLMServiceError("模型响应超时，请稍后重试") from exc
            except APIConnectionError as exc:
                raise LLMServiceError("无法连接模型服务，请检查网络和接口地址") from exc
            except Exception as exc:
                raise LLMServiceError(f"模型调用失败：{exc}") from exc

        raise LLMServiceError("模型连续两次返回了无效评分结构") from last_error
