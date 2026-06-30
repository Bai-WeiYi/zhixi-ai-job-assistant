"""LangGraph 自适应面试：图只保存流程状态，业务事实仍写入 SQLAlchemy。"""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    AdaptiveInterviewSession,
    AdaptiveInterviewTurn,
    Analysis,
    KnowledgeChunk,
)
from app.schemas import AnalysisResult, InterviewQuestion, KnowledgeReference
from app.services.knowledge import KnowledgeServiceError, retrieve_references
from app.services.llm import LLMService

WORKFLOW_VERSION = "adaptive-interview-v1"


class AdaptiveInterviewState(TypedDict, total=False):
    session_id: int
    analysis_id: int
    user_id: int
    max_rounds: int
    follow_up_threshold: int
    completed_turns: int
    main_question_index: int
    current_turn_id: int
    current_question: dict[str, Any]
    current_source: str
    source_question_number: int | None
    answer_text: str
    references: list[dict[str, Any]]
    last_score: int
    pending_follow_up: dict[str, Any] | None
    report: dict[str, Any] | None
    total_tokens: int
    duration_ms: int
    execution_path: list[dict[str, Any]]


@dataclass
class AdaptiveInterviewContext:
    db: Session
    settings: Settings
    analysis: Analysis
    session: AdaptiveInterviewSession
    llm_service: LLMService
    embedding_service: Any


def _event(state: AdaptiveInterviewState, node: str, started_at: float, detail: str):
    return [
        *state.get("execution_path", []),
        {
            "node": node,
            "duration_ms": round((time.perf_counter() - started_at) * 1000),
            "detail": detail,
        },
    ]


def _analysis_questions(analysis: Analysis) -> list[InterviewQuestion]:
    return AnalysisResult.model_validate_json(analysis.result_json).interview_questions


def _persist_question(
    state: AdaptiveInterviewState,
    context: AdaptiveInterviewContext,
    question: InterviewQuestion,
    source: str,
    source_question_number: int | None,
) -> AdaptiveInterviewTurn:
    turn = AdaptiveInterviewTurn(
        session_id=context.session.id,
        round_number=state.get("completed_turns", 0) + 1,
        question_source=source,
        source_question_number=source_question_number,
        question_text=question.question,
        purpose=question.purpose,
        answer_points_json=json.dumps(question.answer_points, ensure_ascii=False),
    )
    context.db.add(turn)
    context.db.commit()
    context.db.refresh(turn)
    return turn


async def prepare_initial_question(
    state: AdaptiveInterviewState,
    runtime: Runtime[AdaptiveInterviewContext],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    index = state.get("main_question_index", 0)
    question = _analysis_questions(runtime.context.analysis)[index]
    turn = _persist_question(state, runtime.context, question, "main", index + 1)
    return {
        "current_turn_id": turn.id,
        "current_question": question.model_dump(),
        "current_source": "main",
        "source_question_number": index + 1,
        "execution_path": _event(state, "prepare_question", started_at, "选择第 1 道主问题"),
    }


async def await_answer(
    state: AdaptiveInterviewState,
    runtime: Runtime[AdaptiveInterviewContext],
) -> dict[str, Any]:
    del runtime
    answer_text = interrupt(
        {
            "turn_id": state["current_turn_id"],
            "round_number": state.get("completed_turns", 0) + 1,
            "question": state["current_question"],
        }
    )
    return {"answer_text": str(answer_text).strip()}


async def retrieve_context(
    state: AdaptiveInterviewState,
    runtime: Runtime[AdaptiveInterviewContext],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    references: list[KnowledgeReference] = []
    db = runtime.context.db
    has_knowledge = (
        db.scalar(
            select(func.count(KnowledgeChunk.id)).where(
                KnowledgeChunk.user_id == state["user_id"]
            )
        )
        or 0
    ) > 0
    detail = "用户没有知识资料，跳过 RAG"
    if has_knowledge:
        question = InterviewQuestion.model_validate(state["current_question"])
        query_text = f"{question.question}\n考察目的：{question.purpose}"
        try:
            query_vector = (await runtime.context.embedding_service.embed([query_text]))[0]
            references = retrieve_references(
                db,
                state["user_id"],
                query_vector,
                runtime.context.settings,
            )
            detail = f"RAG 召回 {len(references)} 条参考资料"
        except KnowledgeServiceError:
            detail = "Embedding 不可用，降级为基础评分"
    return {
        "references": [item.model_dump() for item in references],
        "execution_path": _event(state, "retrieve_context", started_at, detail),
    }


async def evaluate_answer(
    state: AdaptiveInterviewState,
    runtime: Runtime[AdaptiveInterviewContext],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    context = runtime.context
    question = InterviewQuestion.model_validate(state["current_question"])
    references = [KnowledgeReference.model_validate(item) for item in state.get("references", [])]
    evaluation = await context.llm_service.evaluate_adaptive_answer(
        context.analysis.resume_text,
        context.analysis.job_description,
        question,
        state["answer_text"],
        context.settings.adaptive_interview_follow_up_threshold,
        references=references,
    )
    completed_turns = state.get("completed_turns", 0) + 1
    should_follow_up = (
        completed_turns < state["max_rounds"]
        and evaluation.result.feedback.score
        < context.settings.adaptive_interview_follow_up_threshold
        and state["current_source"] == "main"
        and evaluation.result.follow_up_question is not None
    )
    if completed_turns >= state["max_rounds"]:
        route_decision = "finish"
    elif should_follow_up:
        route_decision = "follow_up"
    else:
        route_decision = "next_main"

    turn = context.db.get(AdaptiveInterviewTurn, state["current_turn_id"])
    if turn is None:
        raise RuntimeError("Adaptive interview turn disappeared")
    turn.answer_text = state["answer_text"]
    turn.feedback_json = evaluation.result.feedback.model_dump_json()
    turn.model_name = evaluation.model_name
    turn.prompt_version = evaluation.prompt_version
    turn.prompt_tokens = evaluation.prompt_tokens
    turn.completion_tokens = evaluation.completion_tokens
    turn.total_tokens = evaluation.total_tokens
    turn.duration_ms = evaluation.duration_ms
    turn.rag_context_json = (
        json.dumps(state.get("references", []), ensure_ascii=False)
        if state.get("references")
        else None
    )
    turn.route_decision = route_decision
    turn.answered_at = datetime.now(timezone.utc)
    context.session.completed_turns = completed_turns
    context.session.total_tokens += evaluation.total_tokens or 0
    context.session.duration_ms += evaluation.duration_ms
    context.db.add_all([turn, context.session])
    context.db.commit()

    return {
        "completed_turns": completed_turns,
        "last_score": evaluation.result.feedback.score,
        "pending_follow_up": (
            evaluation.result.follow_up_question.model_dump()
            if evaluation.result.follow_up_question
            else None
        ),
        "total_tokens": state.get("total_tokens", 0) + (evaluation.total_tokens or 0),
        "duration_ms": state.get("duration_ms", 0) + evaluation.duration_ms,
        "execution_path": _event(
            state,
            "evaluate_answer",
            started_at,
            f"评分 {evaluation.result.feedback.score}，路由到 {route_decision}",
        ),
    }


def route_after_evaluation(state: AdaptiveInterviewState) -> str:
    if state["completed_turns"] >= state["max_rounds"]:
        return "finish"
    if (
        state.get("last_score", 100) < state.get("follow_up_threshold", 60)
        and state.get("current_source") == "main"
        and state.get("pending_follow_up")
    ):
        return "follow_up"
    return "next_main"


async def prepare_follow_up(
    state: AdaptiveInterviewState,
    runtime: Runtime[AdaptiveInterviewContext],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    question = InterviewQuestion.model_validate(state["pending_follow_up"])
    turn = _persist_question(
        state,
        runtime.context,
        question,
        "follow_up",
        state.get("source_question_number"),
    )
    return {
        "current_turn_id": turn.id,
        "current_question": question.model_dump(),
        "current_source": "follow_up",
        "answer_text": "",
        "references": [],
        "pending_follow_up": None,
        "execution_path": _event(state, "prepare_follow_up", started_at, "低分触发针对性追问"),
    }


async def prepare_next_main(
    state: AdaptiveInterviewState,
    runtime: Runtime[AdaptiveInterviewContext],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    index = state.get("main_question_index", 0) + 1
    question = _analysis_questions(runtime.context.analysis)[index]
    turn = _persist_question(state, runtime.context, question, "main", index + 1)
    return {
        "main_question_index": index,
        "current_turn_id": turn.id,
        "current_question": question.model_dump(),
        "current_source": "main",
        "source_question_number": index + 1,
        "answer_text": "",
        "references": [],
        "pending_follow_up": None,
        "execution_path": _event(
            state,
            "prepare_next_main",
            started_at,
            f"切换到第 {index + 1} 道主问题",
        ),
    }


async def generate_report(
    state: AdaptiveInterviewState,
    runtime: Runtime[AdaptiveInterviewContext],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    context = runtime.context
    turns = context.db.scalars(
        select(AdaptiveInterviewTurn)
        .where(AdaptiveInterviewTurn.session_id == context.session.id)
        .order_by(AdaptiveInterviewTurn.round_number)
    ).all()
    summaries = [
        {
            "round": turn.round_number,
            "source": turn.question_source,
            "question": turn.question_text,
            "answer": turn.answer_text,
            "feedback": json.loads(turn.feedback_json or "{}"),
        }
        for turn in turns
        if turn.answer_text and turn.feedback_json
    ]
    result = await context.llm_service.generate_adaptive_report(
        context.analysis.resume_text,
        context.analysis.job_description,
        summaries,
    )
    context.session.status = "completed"
    context.session.current_node = "completed"
    context.session.report_json = result.report.model_dump_json()
    context.session.report_model_name = result.model_name
    context.session.report_prompt_version = result.prompt_version
    context.session.total_tokens += result.total_tokens or 0
    context.session.duration_ms += result.duration_ms
    context.session.completed_at = datetime.now(timezone.utc)
    context.db.add(context.session)
    context.db.commit()
    return {
        "report": result.report.model_dump(),
        "total_tokens": state.get("total_tokens", 0) + (result.total_tokens or 0),
        "duration_ms": state.get("duration_ms", 0) + result.duration_ms,
        "execution_path": _event(state, "generate_report", started_at, "生成五轮综合面试报告"),
    }


def build_adaptive_interview_graph(checkpointer):
    builder = StateGraph(
        AdaptiveInterviewState,
        context_schema=AdaptiveInterviewContext,
    )
    builder.add_node("prepare_initial_question", prepare_initial_question)
    builder.add_node("await_answer", await_answer)
    builder.add_node("retrieve_context", retrieve_context)
    builder.add_node("evaluate_answer", evaluate_answer)
    builder.add_node("prepare_follow_up", prepare_follow_up)
    builder.add_node("prepare_next_main", prepare_next_main)
    builder.add_node("generate_report", generate_report)

    builder.add_edge(START, "prepare_initial_question")
    builder.add_edge("prepare_initial_question", "await_answer")
    builder.add_edge("await_answer", "retrieve_context")
    builder.add_edge("retrieve_context", "evaluate_answer")
    builder.add_conditional_edges(
        "evaluate_answer",
        route_after_evaluation,
        {
            "follow_up": "prepare_follow_up",
            "next_main": "prepare_next_main",
            "finish": "generate_report",
        },
    )
    builder.add_edge("prepare_follow_up", "await_answer")
    builder.add_edge("prepare_next_main", "await_answer")
    builder.add_edge("generate_report", END)
    return builder.compile(checkpointer=checkpointer, name=WORKFLOW_VERSION)
