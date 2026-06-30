import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.config import Settings, get_settings
from app.database import get_db
from app.models import (
    AdaptiveInterviewSession,
    AdaptiveInterviewTurn,
    Analysis,
    User,
)
from app.schemas import (
    AdaptiveInterviewReport,
    AdaptiveInterviewSessionListItem,
    AdaptiveInterviewSessionResponse,
    AdaptiveQuestionResponse,
    AdaptiveTurnAnswer,
    AdaptiveTurnResponse,
    InterviewFeedback,
    KnowledgeReference,
    WorkflowTraceEvent,
)
from app.services.adaptive_interview import (
    WORKFLOW_VERSION,
    AdaptiveInterviewContext,
)
from app.services.llm import LLMServiceError
from app.services.usage import (
    INTERVIEW_OPERATION,
    UsageLimitExceeded,
    claim_usage,
    finish_usage,
)

router = APIRouter()


def _service_error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _owned_analysis(db: Session, analysis_id: int, user_id: int) -> Analysis:
    record = db.scalar(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.user_id == user_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="分析记录不存在")
    return record


def _owned_session(db: Session, session_id: int, user_id: int) -> AdaptiveInterviewSession:
    record = db.scalar(
        select(AdaptiveInterviewSession).where(
            AdaptiveInterviewSession.id == session_id,
            AdaptiveInterviewSession.user_id == user_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="自适应面试不存在")
    return record


def _turn_response(turn: AdaptiveInterviewTurn) -> AdaptiveTurnResponse:
    return AdaptiveTurnResponse(
        id=turn.id,
        round_number=turn.round_number,
        source=turn.question_source,
        source_question_number=turn.source_question_number,
        question=turn.question_text,
        purpose=turn.purpose,
        answer_text=turn.answer_text,
        feedback=(
            InterviewFeedback.model_validate_json(turn.feedback_json)
            if turn.feedback_json
            else None
        ),
        model_name=turn.model_name,
        prompt_version=turn.prompt_version,
        duration_ms=turn.duration_ms,
        total_tokens=turn.total_tokens,
        references=(
            [KnowledgeReference.model_validate(item) for item in json.loads(turn.rag_context_json)]
            if turn.rag_context_json
            else []
        ),
        route_decision=turn.route_decision,
        created_at=turn.created_at,
        answered_at=turn.answered_at,
    )


def _session_response(session: AdaptiveInterviewSession) -> AdaptiveInterviewSessionResponse:
    turns = sorted(session.turns, key=lambda item: item.round_number)
    current_turn = next((turn for turn in reversed(turns) if turn.answer_text is None), None)
    current_question = None
    if current_turn is not None and session.status != "completed":
        current_question = AdaptiveQuestionResponse(
            turn_id=current_turn.id,
            round_number=current_turn.round_number,
            source=current_turn.question_source,
            source_question_number=current_turn.source_question_number,
            question=current_turn.question_text,
            purpose=current_turn.purpose,
            answer_points=json.loads(current_turn.answer_points_json),
        )
    return AdaptiveInterviewSessionResponse(
        id=session.id,
        analysis_id=session.analysis_id,
        status=session.status,
        workflow_version=session.workflow_version,
        max_rounds=session.max_rounds,
        completed_turns=session.completed_turns,
        current_node=session.current_node,
        current_question=current_question,
        turns=[_turn_response(turn) for turn in turns],
        report=(
            AdaptiveInterviewReport.model_validate_json(session.report_json)
            if session.report_json
            else None
        ),
        execution_path=[
            WorkflowTraceEvent.model_validate(item)
            for item in json.loads(session.execution_path_json or "[]")
        ],
        total_tokens=session.total_tokens,
        duration_ms=session.duration_ms,
        created_at=session.created_at,
        updated_at=session.updated_at,
        completed_at=session.completed_at,
    )


def _graph_context(
    request: Request,
    db: Session,
    settings: Settings,
    analysis: Analysis,
    session: AdaptiveInterviewSession,
) -> AdaptiveInterviewContext:
    return AdaptiveInterviewContext(
        db=db,
        settings=settings,
        analysis=analysis,
        session=session,
        llm_service=request.app.state.llm_service,
        embedding_service=request.app.state.embedding_service,
    )


async def _sync_graph_state(request: Request, db: Session, session: AdaptiveInterviewSession):
    graph = request.app.state.adaptive_interview_graph
    snapshot = await graph.aget_state(
        {"configurable": {"thread_id": session.thread_id}}
    )
    values = snapshot.values or {}
    session.execution_path_json = json.dumps(
        values.get("execution_path", []),
        ensure_ascii=False,
    )
    session.total_tokens = values.get("total_tokens", session.total_tokens)
    session.duration_ms = values.get("duration_ms", session.duration_ms)
    if snapshot.next:
        session.current_node = snapshot.next[0]
        session.status = "awaiting_answer" if snapshot.next[0] == "await_answer" else "processing"
    elif values.get("report"):
        session.current_node = "completed"
        session.status = "completed"
    db.add(session)
    db.commit()
    db.refresh(session)
    return snapshot


@router.post(
    "/analyses/{analysis_id}/adaptive-interviews",
    response_model=AdaptiveInterviewSessionResponse,
    status_code=201,
)
async def create_adaptive_interview(
    analysis_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AdaptiveInterviewSessionResponse:
    analysis = _owned_analysis(db, analysis_id, current_user.id)
    session = AdaptiveInterviewSession(
        analysis_id=analysis.id,
        user_id=current_user.id,
        thread_id=str(uuid4()),
        status="processing",
        workflow_version=WORKFLOW_VERSION,
        max_rounds=settings.adaptive_interview_rounds,
        completed_turns=0,
        current_node="prepare_initial_question",
        execution_path_json="[]",
        total_tokens=0,
        duration_ms=0,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    graph = request.app.state.adaptive_interview_graph
    await graph.ainvoke(
        {
            "session_id": session.id,
            "analysis_id": analysis.id,
            "user_id": current_user.id,
            "max_rounds": session.max_rounds,
            "follow_up_threshold": settings.adaptive_interview_follow_up_threshold,
            "completed_turns": 0,
            "main_question_index": 0,
            "total_tokens": 0,
            "duration_ms": 0,
            "execution_path": [],
        },
        {"configurable": {"thread_id": session.thread_id}},
        context=_graph_context(request, db, settings, analysis, session),
    )
    await _sync_graph_state(request, db, session)
    return _session_response(session)


@router.get(
    "/analyses/{analysis_id}/adaptive-interviews",
    response_model=list[AdaptiveInterviewSessionListItem],
)
def list_adaptive_interviews(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AdaptiveInterviewSessionListItem]:
    _owned_analysis(db, analysis_id, current_user.id)
    sessions = db.scalars(
        select(AdaptiveInterviewSession)
        .where(
            AdaptiveInterviewSession.analysis_id == analysis_id,
            AdaptiveInterviewSession.user_id == current_user.id,
        )
        .order_by(AdaptiveInterviewSession.created_at.desc())
    ).all()
    return [
        AdaptiveInterviewSessionListItem(
            id=session.id,
            status=session.status,
            completed_turns=session.completed_turns,
            max_rounds=session.max_rounds,
            overall_score=(
                json.loads(session.report_json)["overall_score"]
                if session.report_json
                else None
            ),
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
        for session in sessions
    ]


@router.get(
    "/adaptive-interviews/{session_id}",
    response_model=AdaptiveInterviewSessionResponse,
)
def get_adaptive_interview(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdaptiveInterviewSessionResponse:
    return _session_response(_owned_session(db, session_id, current_user.id))


@router.patch(
    "/adaptive-interviews/{session_id}/turns/{turn_id}",
    response_model=AdaptiveInterviewSessionResponse,
)
async def answer_adaptive_turn(
    session_id: int,
    turn_id: int,
    payload: AdaptiveTurnAnswer,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AdaptiveInterviewSessionResponse:
    session = _owned_session(db, session_id, current_user.id)
    if session.status == "completed":
        raise HTTPException(status_code=409, detail="这场自适应面试已经完成")
    turn = db.scalar(
        select(AdaptiveInterviewTurn).where(
            AdaptiveInterviewTurn.id == turn_id,
            AdaptiveInterviewTurn.session_id == session.id,
        )
    )
    if turn is None:
        raise HTTPException(status_code=404, detail="面试轮次不存在")
    if turn.answer_text is not None and turn.answer_text != payload.answer_text:
        raise HTTPException(status_code=409, detail="已提交的回答不能修改")
    if turn.answer_text is None:
        current_turn = db.scalar(
            select(AdaptiveInterviewTurn)
            .where(
                AdaptiveInterviewTurn.session_id == session.id,
                AdaptiveInterviewTurn.answer_text.is_(None),
            )
            .order_by(AdaptiveInterviewTurn.round_number.desc())
        )
        if current_turn is not None and current_turn.id != turn.id:
            raise HTTPException(status_code=409, detail="只能回答当前面试题")

    analysis = _owned_analysis(db, session.analysis_id, current_user.id)
    graph = request.app.state.adaptive_interview_graph
    config = {"configurable": {"thread_id": session.thread_id}}
    snapshot = await graph.aget_state(config)

    # 完全相同的重复请求直接返回；报告节点失败时则从失败节点继续，不重复回答。
    if turn.answer_text == payload.answer_text and (
        not snapshot.next or snapshot.next[0] == "await_answer"
    ):
        return _session_response(session)

    usage_event = None
    if turn.answer_text is None:
        try:
            usage_event = claim_usage(db, current_user.id, INTERVIEW_OPERATION, settings)
        except UsageLimitExceeded as exc:
            raise HTTPException(
                status_code=429,
                detail={"code": "usage_limit_exceeded", "message": "今日 AI 评分额度已用完"},
                headers={
                    "Retry-After": str(
                        max(
                            1,
                            int(
                                (
                                    exc.reset_at
                                    - datetime.now(timezone.utc)
                                ).total_seconds()
                            ),
                        )
                    )
                },
            ) from exc

    try:
        command = (
            Command(resume=payload.answer_text)
            if snapshot.next and snapshot.next[0] == "await_answer"
            else None
        )
        await graph.ainvoke(
            command,
            config,
            context=_graph_context(request, db, settings, analysis, session),
        )
    except LLMServiceError as exc:
        if usage_event is not None:
            finish_usage(db, usage_event, "failed")
        await _sync_graph_state(request, db, session)
        raise HTTPException(
            status_code=502,
            detail=_service_error_detail(exc.code, exc.message),
        ) from exc

    if usage_event is not None:
        finish_usage(db, usage_event, "succeeded")
    await _sync_graph_state(request, db, session)
    return _session_response(session)
