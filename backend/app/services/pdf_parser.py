from io import BytesIO

from fastapi import HTTPException, UploadFile, status
from pypdf import PdfReader

from app.schemas import ParsedResume


async def parse_resume_pdf(file: UploadFile, max_size_mb: int) -> ParsedResume:
    """读取带文本层的 PDF；扫描图片型 PDF 暂不支持。"""
    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="仅支持 PDF 文件")

    content = await file.read()
    if len(content) > max_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF 文件过大")

    try:
        reader = PdfReader(BytesIO(content))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:
        raise HTTPException(status_code=400, detail="PDF 无法解析，请确认文件未损坏") from exc

    text = "\n\n".join(page for page in pages if page).strip()
    if len(text) < 30:
        raise HTTPException(status_code=422, detail="未提取到足够文本，扫描版 PDF 暂不支持")

    return ParsedResume(text=text, page_count=len(reader.pages), character_count=len(text))
