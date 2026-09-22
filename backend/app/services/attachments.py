import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

from fastapi import HTTPException
from ..database import DATA, ROOT

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 9000
UPLOAD_DIR = DATA / "uploads"
OCR_MODEL_DIR = ROOT / "models" / "tesseract"
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".css",
    ".js", ".jsx", ".ts", ".tsx", ".py", ".java", ".c", ".cpp", ".h",
    ".sql", ".yaml", ".yml", ".xml", ".log", ".ipynb",
}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}


def safe_filename(value: str | None):
    name = Path(value or "file").name.strip()
    return name[:200] or "file"


def extract_text(filename: str, content: bytes, max_chars=MAX_EXTRACTED_CHARS):
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
    return text[:max_chars]


def _decode_text(content: bytes):
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(422, "无法识别文本编码，请将文件保存为 UTF-8 后重试。")


def _extract_pdf(content: bytes):
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "upload.pdf"
        target = Path(directory) / "upload.txt"
        source.write_bytes(content)
        extracted = ""
        command = _find_command("pdftotext", _miktex_binary("pdftotext.exe"))
        if command:
            result = subprocess.run(
                [command, "-layout", "-f", "1", "-l", "100", "-enc", "UTF-8", str(source), str(target)],
                capture_output=True, timeout=30, check=False,
            )
            if not result.returncode and target.exists():
                extracted = target.read_text(encoding="utf-8", errors="replace").strip()
        if len(extracted) >= 80:
            return extracted
        try:
            ocr_text = _ocr_pdf(source, Path(directory))
            return ocr_text if len(ocr_text) > len(extracted) else extracted
        except HTTPException:
            if extracted:
                return extracted
            raise


def _ocr_pdf(source: Path, directory: Path):
    renderer = _find_command("pdftoppm", _miktex_binary("pdftoppm.exe"))
    tesseract = _find_command(
        "tesseract",
        str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR" / "tesseract.exe"),
    )
    languages = [name for name in ("chi_sim", "eng") if (OCR_MODEL_DIR / f"{name}.traineddata").is_file()]
    if not renderer or not tesseract or not languages:
        raise HTTPException(415, "扫描版 PDF 需要本地 OCR 组件。请运行 scripts/setup_ocr.ps1 后重试。")
    prefix = directory / "ocr-page"
    rendered = subprocess.run(
        [renderer, "-f", "1", "-l", "20", "-r", "220", "-png", str(source), str(prefix)],
        capture_output=True, timeout=90, check=False,
    )
    pages = sorted(directory.glob("ocr-page-*.png"))
    if rendered.returncode or not pages:
        raise HTTPException(422, "无法将扫描版 PDF 转换为图片，文件可能已损坏或加密。")
    texts = []
    for page in pages:
        result = subprocess.run(
            [tesseract, str(page), "stdout", "--tessdata-dir", str(OCR_MODEL_DIR),
             "-l", "+".join(languages), "--psm", "6"],
            capture_output=True, timeout=45, check=False,
        )
        if not result.returncode:
            texts.append(result.stdout.decode("utf-8", errors="replace"))
    text = "\n\n".join(texts).strip()
    if not text:
        raise HTTPException(422, "OCR 没有识别出文字，请确认扫描清晰度或改用更清晰的 PDF。")
    return "[以下文字由 OCR 识别，导入前必须仔细核对]\n" + text


def _miktex_binary(name):
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    return str(local / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64" / name) if local else ""


def _find_command(name, candidate=""):
    found = shutil.which(name)
    if found:
        return found
    return candidate if candidate and Path(candidate).is_file() else None


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
