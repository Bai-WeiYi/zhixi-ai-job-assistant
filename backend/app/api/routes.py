import json
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models import Analysis, InterviewAttempt, User
from app.schemas import (
    AnalysisCreate,
    AnalysisListItem,
    AnalysisResponse,
    AnalysisResult,
    AuthResponse,
    HealthResponse,
    InterviewAttemptCreate,
    InterviewAttemptResponse,
    InterviewFeedback,
    ParsedResume,
    UsageSummary,
    UserCredentials,
    UserResponse,
)
from app.services.auth import create_access_token, hash_password, verify_password
from app.services.llm import LLMAnalysis, LLMInterviewEvaluation, LLMServiceError
from app.services.pdf_parser import parse_resume_pdf
from app.services.usage import (
    ANALYSIS_OPERATION,
    INTERVIEW_OPERATION,
    UsageLimitExceeded,
    build_usage_summary,
    claim_usage,
    finish_usage,
)

router = APIRouter()


def build_user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, created_at=user.created_at)


def build_auth_response(user: User, settings: Settings) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(user.id, settings),
        user=build_user_response(user),
    )


def get_owned_analysis(db: Session, analysis_id: int, user_id: int) -> Analysis:
    """只查询当前用户的数据，对越权访问也返回 404。"""
    record = db.scalar(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.user_id == user_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="分析记录不存在")
    return record


def build_response(record: Analysis) -> AnalysisResponse:
    return AnalysisResponse(
        id=record.id,
        result=AnalysisResult.model_validate_json(record.result_json),
        model_name=record.model_name,
        duration_ms=record.duration_ms,
        prompt_tokens=record.prompt_tokens,
        completion_tokens=record.completion_tokens,
        total_tokens=record.total_tokens,
        created_at=record.created_at,
    )


def build_attempt_response(record: InterviewAttempt) -> InterviewAttemptResponse:
    return InterviewAttemptResponse(
        id=record.id,
        analysis_id=record.analysis_id,
        question_number=record.question_number,
        question_text=record.question_text,
        answer_text=record.answer_text,
        feedback=InterviewFeedback.model_validate_json(record.feedback_json),
        model_name=record.model_name,
        duration_ms=record.duration_ms,
        prompt_tokens=record.prompt_tokens,
        completion_tokens=record.completion_tokens,
        total_tokens=record.total_tokens,
        created_at=record.created_at,
    )


def raise_usage_limit(exc: UsageLimitExceeded) -> None:
    retry_after = max(
        math.ceil((exc.reset_at - datetime.now(timezone.utc)).total_seconds()),
        1,
    )
    raise HTTPException(
        status_code=429,
        detail="今日 AI 使用次数已达上限，请在额度重置后再试",
        headers={"Retry-After": str(retry_after)},
    )


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="ok")


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(
    payload: UserCredentials,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    if db.scalar(select(User).where(User.email == payload.email)) is not None:
        raise HTTPException(status_code=409, detail="该邮箱已注册")

    is_first_user = db.scalar(select(User.id).limit(1)) is None
    user = User(email=str(payload.email), password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.flush()
        if is_first_user:
            # 让升级前的本地记录继续可见，不覆盖已经有归属的数据。
            db.execute(
                update(Analysis)
                .where(Analysis.user_id.is_(None))
                .values(user_id=user.id)
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该邮箱已注册") from exc
    db.refresh(user)
    return build_auth_response(user, settings)


@router.post("/auth/login", response_model=AuthResponse)
def login(
    payload: UserCredentials,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    return build_auth_response(user, settings)


@router.get("/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return build_user_response(current_user)


@router.get("/usage", response_model=UsageSummary)
def get_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> UsageSummary:
    return build_usage_summary(db, current_user.id, settings)


@router.post("/resumes/parse", response_model=ParsedResume)
async def parse_resume(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> ParsedResume:
    del current_user
    return await parse_resume_pdf(file, settings.max_pdf_size_mb)


@router.post("/analyses", response_model=AnalysisResponse, status_code=201)
async def create_analysis(
    payload: AnalysisCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AnalysisResponse:
    try:
        usage_event = claim_usage(
            db,
            current_user.id,
            ANALYSIS_OPERATION,
            settings,
        )
    except UsageLimitExceeded as exc:
        raise_usage_limit(exc)

    try:
        analysis: LLMAnalysis = await request.app.state.llm_service.analyze(
            payload.resume_text,
            payload.job_description,
        )
    except LLMServiceError as exc:
        finish_usage(db, usage_event, "failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    record = Analysis(
        user_id=current_user.id,
        resume_text=payload.resume_text,
        job_description=payload.job_description,
        result_json=analysis.result.model_dump_json(),
        model_name=analysis.model_name,
        prompt_tokens=analysis.prompt_tokens,
        completion_tokens=analysis.completion_tokens,
        total_tokens=analysis.total_tokens,
        duration_ms=analysis.duration_ms,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    finish_usage(db, usage_event, "succeeded")
    return build_response(record)


@router.get("/analyses", response_model=list[AnalysisListItem])
def list_analyses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AnalysisListItem]:
    records = db.scalars(
        select(Analysis)
        .where(Analysis.user_id == current_user.id)
        .order_by(Analysis.created_at.desc())
    ).all()
    items: list[AnalysisListItem] = []
    for record in records:
        result = json.loads(record.result_json)
        preview = " ".join(record.job_description.split())
        items.append(
            AnalysisListItem(
                id=record.id,
                match_score=result["match_score"],
                summary=result["summary"],
                job_description_preview=preview[:100],
                model_name=record.model_name,
                created_at=record.created_at,
            )
        )
    return items


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalysisResponse:
    record = get_owned_analysis(db, analysis_id, current_user.id)
    return build_response(record)


@router.post(
    "/analyses/{analysis_id}/questions/{question_number}/attempts",
    response_model=InterviewAttemptResponse,
    status_code=201,
)
async def create_interview_attempt(
    analysis_id: int,
    question_number: int,
    payload: InterviewAttemptCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> InterviewAttemptResponse:
    record = get_owned_analysis(db, analysis_id, current_user.id)
    if question_number < 1 or question_number > 8:
        raise HTTPException(status_code=422, detail="题号必须在 1 到 8 之间")

    result = AnalysisResult.model_validate_json(record.result_json)
    question = result.interview_questions[question_number - 1]
    try:
        usage_event = claim_usage(
            db,
            current_user.id,
            INTERVIEW_OPERATION,
            settings,
        )
    except UsageLimitExceeded as exc:
        raise_usage_limit(exc)

    try:
        evaluation: LLMInterviewEvaluation = (
            await request.app.state.llm_service.evaluate_interview_answer(
                record.resume_text,
                record.job_description,
                question,
                payload.answer_text,
            )
        )
    except LLMServiceError as exc:
        finish_usage(db, usage_event, "failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    attempt = InterviewAttempt(
        analysis_id=record.id,
        question_number=question_number,
        question_text=question.question,
        answer_text=payload.answer_text,
        feedback_json=evaluation.feedback.model_dump_json(),
        model_name=evaluation.model_name,
        prompt_tokens=evaluation.prompt_tokens,
        completion_tokens=evaluation.completion_tokens,
        total_tokens=evaluation.total_tokens,
        duration_ms=evaluation.duration_ms,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    finish_usage(db, usage_event, "succeeded")
    return build_attempt_response(attempt)


@router.get(
    "/analyses/{analysis_id}/interview-attempts",
    response_model=list[InterviewAttemptResponse],
)
def list_interview_attempts(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[InterviewAttemptResponse]:
    get_owned_analysis(db, analysis_id, current_user.id)

    records = db.scalars(
        select(InterviewAttempt)
        .where(InterviewAttempt.analysis_id == analysis_id)
        .order_by(InterviewAttempt.created_at.asc(), InterviewAttempt.id.asc())
    ).all()
    return [build_attempt_response(record) for record in records]


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    record = get_owned_analysis(db, analysis_id, current_user.id)
    db.delete(record)
    db.commit()
    return Response(status_code=204)
