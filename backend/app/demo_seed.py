"""写入本地演示数据，便于无网络时展示完整产品流程。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Analysis, InterviewAttempt, User
from app.schemas import AnalysisResult, InterviewFeedback
from app.services.auth import hash_password

DEMO_MODEL_NAME = "demo-local"
DEMO_PROMPT_VERSION = "demo-v1"
DEMO_RESUME = """候选人有 2 年 Python 开发经验，熟悉 FastAPI、SQLAlchemy、SQLite 和 REST API。
独立完成 AI 求职面试助手，负责需求拆解、后端接口、DeepSeek 接入、结构化输出校验、
Next.js 前端联调和自动化测试。项目支持 PDF 简历解析、岗位匹配分析和模拟面试评分。"""
DEMO_JOB_DESCRIPTION = """【演示岗位】AI 应用全栈工程师
负责基于 Python 和 FastAPI 开发大模型应用，完成模型 API 接入、结构化输出校验、
数据库设计以及 Next.js 前端协作。要求掌握 SQL、REST API、Git 和基础测试能力，
有完整 AI 应用项目经验者优先。"""


def demo_result() -> AnalysisResult:
    """返回固定且通过 Pydantic 校验的岗位分析。"""
    questions = [
        (
            "请介绍这个 AI 求职助手的完整请求链路。",
            "考察全栈链路理解和表达能力",
            ["说明前端提交", "说明 FastAPI 与 Pydantic", "说明模型调用与数据库保存"],
        ),
        (
            "为什么要校验大模型的结构化输出？",
            "考察对大模型不确定性的理解",
            ["解释 JSON 可能不合法", "说明 Pydantic 规则", "说明失败重试"],
        ),
        (
            "为什么选择 FastAPI，而不是 Flask？",
            "考察技术选型能力",
            ["类型提示与校验", "自动接口文档", "异步模型调用"],
        ),
        (
            "如何设计分析记录和面试练习记录之间的关系？",
            "考察数据库建模能力",
            ["一对多关系", "外键", "级联删除"],
        ),
        (
            "如果 DeepSeek 超时，前后端分别如何处理？",
            "考察异常处理与用户体验",
            ["后端捕获超时", "返回明确状态码", "前端保留输入并允许重试"],
        ),
        (
            "如何保证同一道题的多次练习可以对比？",
            "考察业务建模与统计逻辑",
            ["每次保存独立记录", "按题号筛选", "平均分取每题最新记录"],
        ),
        (
            "这个项目目前有哪些边界，后续会如何演进？",
            "考察范围控制和演进思路",
            ["说明本地多用户", "说明暂不支持 OCR", "说明 PostgreSQL 和部署方向"],
        ),
        (
            "你为这个项目设计了哪些测试？",
            "考察工程质量意识",
            ["接口与输入校验", "模型异常和重试", "前端交互与构建检查"],
        ),
    ]
    return AnalysisResult(
        match_score=86,
        summary="候选人的 Python、FastAPI 和大模型应用经验与岗位高度相关，已经具备完整项目闭环。",
        strengths=[
            "具备 Python、FastAPI 和 SQLAlchemy 的实际项目经验",
            "理解大模型结构化输出校验与失败重试",
            "能够完成 Next.js 前端联调和自动化测试",
        ],
        gaps=[
            "缺少公开部署和生产环境运维经验",
            "暂未覆盖刷新令牌、并发控制和成本监控",
        ],
        resume_suggestions=[
            "补充接口数量、测试数量和构建结果等可量化信息",
            "突出模型输出校验、异常处理和多次练习记录等工程亮点",
            "准备一段 3 分钟项目介绍，按照问题、方案、难点和结果展开",
        ],
        interview_questions=[
            {"question": question, "purpose": purpose, "answer_points": points}
            for question, purpose, points in questions
        ],
    )


def feedback(
    score: int,
    summary: str,
    strengths: list[str],
    improvements: list[str],
) -> InterviewFeedback:
    return InterviewFeedback(
        score=score,
        summary=summary,
        strengths=strengths,
        improvements=improvements,
        suggested_answer_points=["先说明业务背景", "再解释关键数据流和技术取舍", "最后总结结果与改进"],
    )


def seed_demo_data(
    db: Session,
    owner_id: int | None = None,
) -> tuple[Analysis, bool]:
    """幂等写入演示记录；已存在时直接返回，不修改用户数据。"""
    existing_query = select(Analysis).where(
        Analysis.model_name == DEMO_MODEL_NAME,
        Analysis.job_description == DEMO_JOB_DESCRIPTION,
    )
    if owner_id is not None:
        existing_query = existing_query.where(Analysis.user_id == owner_id)
    existing = db.scalar(existing_query)
    if existing is not None:
        return existing, False

    result = demo_result()
    if owner_id is None:
        owner_id = db.scalar(
            select(User.id).order_by(User.created_at.asc(), User.id.asc())
        )
    analysis = Analysis(
        user_id=owner_id,
        resume_text=DEMO_RESUME,
        job_description=DEMO_JOB_DESCRIPTION,
        result_json=result.model_dump_json(),
        model_name=DEMO_MODEL_NAME,
        prompt_version=DEMO_PROMPT_VERSION,
        prompt_tokens=1280,
        completion_tokens=1620,
        total_tokens=2900,
        duration_ms=6840,
    )
    db.add(analysis)
    db.flush()

    attempts = [
        (
            1,
            "第一次回答时，我主要介绍了前端把简历和 JD 提交给 FastAPI，然后后端调用模型并把结果保存到数据库。",
            feedback(
                72,
                "已经覆盖主链路，但结构化校验和异常处理说明不够完整。",
                ["能够说清前后端职责", "提到了模型调用和持久化"],
                ["补充 Pydantic 校验", "说明失败重试和错误返回"],
            ),
        ),
        (
            1,
            "前端通过 POST 提交简历和 JD，FastAPI 先使用 Pydantic 校验输入，再调用 DeepSeek。模型返回 JSON 后再次用 Pydantic 校验，失败自动重试一次；成功后 SQLAlchemy 保存到 SQLite，最后 React 根据响应更新页面。",
            feedback(
                91,
                "请求链路完整，能够清楚说明输入校验、模型校验、持久化和页面更新。",
                ["顺序清晰", "覆盖了两次 Pydantic 校验", "说明了失败重试"],
                ["可以补充 HTTP 状态码和耗时记录"],
            ),
        ),
        (
            2,
            "大模型输出存在随机性，即使要求 JSON 也可能缺字段或类型错误，所以程序用 InterviewFeedback 等 Pydantic 模型校验。第一次失败会追加纠错提示重试，第二次仍失败就返回可读错误。",
            feedback(
                89,
                "准确解释了结构化校验的原因、实现方式和失败策略。",
                ["理解模型输出的不确定性", "说明了校验模型和重试流程"],
                ["可以举一个 score 超出 0 到 100 的具体例子"],
            ),
        ),
        (
            4,
            "Analysis 和 InterviewAttempt 是一对多关系，答题记录通过 analysis_id 外键关联分析。删除分析时使用 ORM 级联删除，保证不会留下失去所属分析的记录。",
            feedback(
                87,
                "数据库关系与删除策略说明准确，表达简洁。",
                ["说明了一对多与外键", "考虑了关联数据清理"],
                ["可以补充为什么同题多次作答要保存为独立行"],
            ),
        ),
    ]
    for question_number, answer_text, attempt_feedback in attempts:
        question = result.interview_questions[question_number - 1]
        db.add(
            InterviewAttempt(
                analysis_id=analysis.id,
                question_number=question_number,
                question_text=question.question,
                answer_text=answer_text,
                feedback_json=attempt_feedback.model_dump_json(),
                model_name=DEMO_MODEL_NAME,
                prompt_version=DEMO_PROMPT_VERSION,
                prompt_tokens=620,
                completion_tokens=380,
                total_tokens=1000,
                duration_ms=2450,
            )
        )

    db.commit()
    db.refresh(analysis)
    return analysis, True


def ensure_portfolio_user(
    db: Session,
    email: str,
    password: str,
) -> tuple[User, bool]:
    """生产环境创建专用演示账号；已有账号时不覆盖密码。"""
    normalized_email = email.strip().lower()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        return existing, False

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, True


def main() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        if settings.portfolio_user_email or settings.portfolio_user_password:
            if not settings.portfolio_user_email or not settings.portfolio_user_password:
                raise RuntimeError(
                    "PORTFOLIO_USER_EMAIL 和 PORTFOLIO_USER_PASSWORD 必须同时配置"
                )
            user, user_created = ensure_portfolio_user(
                db,
                settings.portfolio_user_email,
                settings.portfolio_user_password,
            )
            analysis, created = seed_demo_data(db, owner_id=user.id)
            user_action = "已创建" if user_created else "已存在"
            print(f"作品集演示账号{user_action}：{user.email}")
        else:
            analysis, created = seed_demo_data(db)
    action = "已创建" if created else "已存在"
    print(f"演示记录{action}，分析 ID：{analysis.id}")


if __name__ == "__main__":
    main()
