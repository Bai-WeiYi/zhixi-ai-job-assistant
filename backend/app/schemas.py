from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCredentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """邮箱统一转小写，避免大小写造成重复账号。"""
        return str(value).strip().lower()


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class InterviewQuestion(BaseModel):
    question: str = Field(min_length=5, max_length=500)
    purpose: str = Field(min_length=2, max_length=300)
    answer_points: list[str] = Field(min_length=2, max_length=6)


class AnalysisResult(BaseModel):
    match_score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=10, max_length=1000)
    strengths: list[str] = Field(min_length=1, max_length=8)
    gaps: list[str] = Field(min_length=1, max_length=8)
    resume_suggestions: list[str] = Field(min_length=1, max_length=8)
    interview_questions: list[InterviewQuestion] = Field(min_length=8, max_length=8)


class InterviewFeedback(BaseModel):
    """AI 对单道面试回答给出的结构化反馈。"""

    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=10, max_length=1000)
    strengths: list[str] = Field(min_length=1, max_length=6)
    improvements: list[str] = Field(min_length=1, max_length=6)
    suggested_answer_points: list[str] = Field(min_length=2, max_length=8)


class KnowledgeReference(BaseModel):
    document_id: int
    title: str
    content: str
    similarity: float = Field(ge=-1, le=1)


class AnalysisCreate(BaseModel):
    resume_text: str = Field(min_length=30, max_length=30000)
    job_description: str = Field(min_length=30, max_length=15000)

    @field_validator("resume_text", "job_description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("内容不能为空")
        return value


class InterviewAttemptCreate(BaseModel):
    answer_text: str = Field(min_length=20, max_length=5000)

    @field_validator("answer_text", mode="before")
    @classmethod
    def strip_answer(cls, value: str) -> str:
        return value.strip()


class InterviewAttemptResponse(BaseModel):
    id: int
    analysis_id: int
    question_number: int
    question_text: str
    answer_text: str
    feedback: InterviewFeedback
    model_name: str
    prompt_version: str
    duration_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    references: list[KnowledgeReference] = Field(default_factory=list)
    created_at: datetime


class AnalysisResponse(BaseModel):
    id: int
    result: AnalysisResult
    model_name: str
    prompt_version: str
    duration_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    created_at: datetime


class AnalysisListItem(BaseModel):
    id: int
    match_score: int
    summary: str
    job_description_preview: str
    model_name: str
    created_at: datetime


class ParsedResume(BaseModel):
    text: str
    page_count: int
    character_count: int


class HealthResponse(BaseModel):
    status: str
    database: str


class UsageQuota(BaseModel):
    used: int
    limit: int
    remaining: int
    reset_at: datetime


class UsageSummary(BaseModel):
    analysis: UsageQuota
    interview: UsageQuota
    knowledge: UsageQuota


class KnowledgeDocumentResponse(BaseModel):
    id: int
    title: str
    source_type: str
    filename: str | None = None
    character_count: int
    chunk_count: int
    created_at: datetime
