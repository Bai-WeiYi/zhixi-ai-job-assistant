import json
import math
import re
from dataclasses import dataclass
from io import BytesIO

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI
from pypdf import PdfReader
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas import KnowledgeReference


class KnowledgeServiceError(RuntimeError):
    """统一包装知识解析、向量化和检索异常。"""


@dataclass
class ParsedKnowledge:
    text: str
    source_type: str
    filename: str | None


def parse_knowledge_input(
    raw_text: str | None,
    file_content: bytes | None,
    filename: str | None,
    content_type: str | None,
    settings: Settings,
) -> ParsedKnowledge:
    """校验文本或 PDF，并返回统一的纯文本内容。"""
    has_text = bool(raw_text and raw_text.strip())
    has_file = file_content is not None
    if has_text == has_file:
        raise KnowledgeServiceError("请在粘贴文本和上传 PDF 中选择一种")

    if has_text:
        parsed = raw_text.strip()
        source_type = "text"
        source_filename = None
    else:
        if content_type != "application/pdf" and not (filename or "").lower().endswith(".pdf"):
            raise KnowledgeServiceError("知识资料仅支持 PDF 文件")
        if len(file_content or b"") > settings.max_pdf_size_mb * 1024 * 1024:
            raise KnowledgeServiceError(
                f"PDF 文件不能超过 {settings.max_pdf_size_mb} MB"
            )
        try:
            reader = PdfReader(BytesIO(file_content or b""))
            parsed = "\n\n".join(
                (page.extract_text() or "").strip() for page in reader.pages
            ).strip()
        except Exception as exc:
            raise KnowledgeServiceError("PDF 无法解析，请确认文件未损坏") from exc
        if len(parsed) < 30:
            raise KnowledgeServiceError("未提取到足够文本，扫描版 PDF 暂不支持")
        source_type = "pdf"
        source_filename = filename

    if len(parsed) < 30:
        raise KnowledgeServiceError("知识资料至少需要 30 个字符")
    if len(parsed) > settings.knowledge_max_characters:
        raise KnowledgeServiceError(
            f"单份知识资料不能超过 {settings.knowledge_max_characters} 个字符"
        )
    return ParsedKnowledge(parsed, source_type, source_filename)


def chunk_text(content: str, target_size: int = 600, overlap: int = 100) -> list[str]:
    """优先按段落切块，长段落再按固定长度拆分并保留少量重叠。"""
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n+", content) if item.strip()]
    chunks: list[str] = []
    current = ""

    def append_long(value: str) -> None:
        start = 0
        while start < len(value):
            piece = value[start : start + target_size].strip()
            if piece:
                chunks.append(piece)
            if start + target_size >= len(value):
                break
            start += target_size - overlap

    for paragraph in paragraphs:
        if len(paragraph) > target_size:
            if current:
                chunks.append(current)
                current = ""
            append_long(paragraph)
            continue
        candidate = f"{current}\n\n{paragraph}".strip()
        if current and len(candidate) > target_size:
            chunks.append(current)
            prefix = current[-overlap:] if overlap else ""
            current = f"{prefix}\n\n{paragraph}".strip()
        else:
            current = candidate
    if current:
        chunks.append(current)
    return [item for item in chunks if len(item) >= 20]


def serialize_vector(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.10g}" for value in vector) + "]"


def deserialize_vector(value: str | list[float]) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value]
    if not isinstance(value, str):
        return [float(item) for item in value]
    return [float(item) for item in json.loads(value)]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


class EmbeddingService:
    """调用硅基流动兼容接口生成知识片段向量。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.embedding_api_key or "missing-key",
            base_url=settings.embedding_base_url,
            timeout=settings.llm_timeout_seconds,
        )

    async def embed(self, inputs: list[str]) -> list[list[float]]:
        if not self.settings.embedding_api_key:
            raise KnowledgeServiceError("尚未配置 EMBEDDING_API_KEY")
        try:
            response = await self.client.embeddings.create(
                model=self.settings.embedding_model,
                input=inputs,
            )
        except APITimeoutError as exc:
            raise KnowledgeServiceError("向量服务响应超时，请稍后重试") from exc
        except APIConnectionError as exc:
            raise KnowledgeServiceError("无法连接向量服务，请检查网络和接口地址") from exc
        except Exception as exc:
            raise KnowledgeServiceError(f"向量服务调用失败：{exc}") from exc

        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(inputs) or any(
            len(vector) != self.settings.embedding_dimensions for vector in vectors
        ):
            raise KnowledgeServiceError("向量服务返回的数据数量或维度不正确")
        return vectors


def retrieve_references(
    db: Session,
    user_id: int,
    query_vector: list[float],
    settings: Settings,
) -> list[KnowledgeReference]:
    """按用户隔离检索最相关片段，并兼容 SQLite 测试环境。"""
    vector_available = False
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        vector_available = bool(
            db.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
                )
            )
        )

    if vector_available:
        rows = db.execute(
            text(
                """
                SELECT kc.document_id, kd.title, kc.content,
                       1 - (kc.embedding <=> CAST(:query AS vector)) AS similarity
                FROM knowledge_chunks AS kc
                JOIN knowledge_documents AS kd ON kd.id = kc.document_id
                WHERE kc.user_id = :user_id
                ORDER BY kc.embedding <=> CAST(:query AS vector)
                LIMIT :limit
                """
            ),
            {
                "query": serialize_vector(query_vector),
                "user_id": user_id,
                "limit": settings.knowledge_top_k,
            },
        ).all()
        candidates = [
            KnowledgeReference(
                document_id=row.document_id,
                title=row.title,
                content=row.content,
                similarity=float(row.similarity),
            )
            for row in rows
        ]
    else:
        rows = db.execute(
            select(KnowledgeChunk, KnowledgeDocument.title)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeChunk.user_id == user_id)
        ).all()
        candidates = sorted(
            (
                KnowledgeReference(
                    document_id=chunk.document_id,
                    title=title,
                    content=chunk.content,
                    similarity=cosine_similarity(
                        deserialize_vector(chunk.embedding),
                        query_vector,
                    ),
                )
                for chunk, title in rows
            ),
            key=lambda item: item.similarity,
            reverse=True,
        )[: settings.knowledge_top_k]
    return [
        item
        for item in candidates
        if item.similarity >= settings.knowledge_min_similarity
    ]
