import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

from fastapi import HTTPException
from ..database import DATA

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 9000
UPLOAD_DIR = DATA / "uploads"
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".css",
    ".js", ".jsx", ".ts", ".tsx", ".py", ".java", ".c", ".cpp", ".h",
    ".sql", ".yaml", ".yml", ".xml", ".log",
}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}


def safe_filename(value: str | None):
    name = Path(value or "file").name.strip()
    return name[:200] or "file"


def extract_text(filename: str, content: bytes):
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, "暂不支持这种文件。可上传 TXT、Markdown、CSV、JSON、代码、PDF 或 DOCX。")
    try:
        if extension == ".pdf":
            text = _extract_pdf(content)
        elif extension == ".docx":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
            text = "\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
        else:
            text = _decode_text(content)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(422, "无法读取文件内容，请确认文件没有损坏或加密。") from error
    text = text.replace("\x00", "").strip()
    if not text:
        raise HTTPException(422, "文件中没有可读取的文字；扫描版 PDF 暂不支持 OCR。")
    return text[:MAX_EXTRACTED_CHARS]


def _decode_text(content: bytes):
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(422, "无法识别文本编码，请将文件保存为 UTF-8 后重试。")


def _extract_pdf(content: bytes):
    command = shutil.which("pdftotext")
    if not command:
        raise HTTPException(415, "这台电脑没有 PDF 文本解析器，请先转换为 TXT、Markdown 或 DOCX。")
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "upload.pdf"
        target = Path(directory) / "upload.txt"
        source.write_bytes(content)
        result = subprocess.run(
            [command, "-f", "1", "-l", "100", "-enc", "UTF-8", str(source), str(target)],
            capture_output=True, timeout=30, check=False,
        )
        if result.returncode or not target.exists():
            raise HTTPException(422, "无法读取 PDF；文件可能已损坏、加密或只包含扫描图片。")
        return target.read_text(encoding="utf-8", errors="replace")


def save_upload(filename: str, content: bytes):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    storage_name = f"{uuid4().hex}{Path(filename).suffix.lower()}"
    (UPLOAD_DIR / storage_name).write_bytes(content)
    return storage_name


def delete_upload(storage_name: str):
    attachment_path(storage_name).unlink(missing_ok=True)


def attachment_path(storage_name: str):
    return UPLOAD_DIR / Path(storage_name).name


def attachment_dict(row):
    return {
        "id": row.id,
        "filename": row.filename,
        "media_type": row.media_type,
        "size_bytes": row.size_bytes,
        "message_id": row.message_id,
        "created_at": row.created_at,
    }
