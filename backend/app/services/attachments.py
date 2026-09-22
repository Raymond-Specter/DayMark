import csv
import io
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
import zlib
from pathlib import Path
from statistics import median
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
        raise HTTPException(422, "文件中没有识别到可读取的文字，请确认文件清晰且没有损坏或加密。")
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
        embedded = _extract_unigb_pdf(content)
        if len(embedded) >= 80:
            return embedded
        try:
            ocr_text = _ocr_pdf(source, Path(directory))
            return ocr_text if len(ocr_text) > len(extracted) else extracted
        except HTTPException:
            if extracted:
                return extracted
            raise


def _pdf_literal_bytes(value):
    result = bytearray()
    index, depth = 1, 1
    escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while index < len(value) and depth:
        current = value[index]
        if current == 92:  # PDF string escape: backslash
            index += 1
            if index >= len(value):
                break
            escaped = value[index]
            if escaped in escapes:
                result.append(escapes[escaped])
            elif escaped in (40, 41, 92):
                result.append(escaped)
            elif escaped in (10, 13):
                if escaped == 13 and index + 1 < len(value) and value[index + 1] == 10:
                    index += 1
            elif 48 <= escaped <= 55:
                digits = bytes([escaped])
                for _ in range(2):
                    if index + 1 < len(value) and 48 <= value[index + 1] <= 55:
                        index += 1
                        digits += bytes([value[index]])
                    else:
                        break
                result.append(int(digits, 8))
            else:
                result.append(escaped)
        elif current == 40:
            depth += 1
            result.append(current)
        elif current == 41:
            depth -= 1
            if depth:
                result.append(current)
        else:
            result.append(current)
        index += 1
    return bytes(result)


def _unigb_page(stream):
    items, x, y = [], 0.0, 0.0
    matrix = re.compile(rb"1\s+0\s+0\s+1\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+Tm")
    for line in stream.splitlines():
        match = matrix.fullmatch(line.strip())
        if match:
            x, y = float(match.group(1)), float(match.group(2))
            continue
        stripped = line.strip()
        if not stripped.startswith(b"(") or not stripped.endswith(b")Tj"):
            continue
        raw = _pdf_literal_bytes(stripped[:-2])
        if not raw or len(raw) % 2:
            continue
        try:
            text = raw.decode("utf-16-be").replace("\x00", "").strip()
        except UnicodeDecodeError:
            continue
        if text:
            items.append({"x": x, "y": y, "text": text})
    return items


def _format_unigb_pages(pages):
    labels = "一二三四五六日"
    header_page = next((page for page in pages if sum(item["text"] in {f"星期{x}" for x in labels}
                                                       for item in page) >= 3), None)
    if not header_page:
        return ""
    headers = {labels.index(item["text"][-1]): (item["x"], item["y"])
               for item in header_page if item["text"] in {f"星期{x}" for x in labels}}
    spacings = [(headers[b][0] - headers[a][0]) / (b - a)
                for a in headers for b in headers if b > a]
    if not spacings:
        return ""
    spacing = median(spacings)
    origin = median(x - index * spacing for index, (x, _) in headers.items())
    bounds = [origin - spacing / 2] + [origin + (index + .5) * spacing for index in range(6)] + [origin + 6.5 * spacing]
    columns = [[] for _ in labels]
    for page in pages:
        page_headers = [item for item in page if item["text"] in {f"星期{x}" for x in labels}]
        header_y = median(item["y"] for item in page_headers) if page_headers else None
        body = [item for item in page if header_y is None or item["y"] < header_y]
        for index in range(len(labels)):
            column = [item for item in body if bounds[index] <= item["x"] < bounds[index + 1]]
            if column:
                groups = []
                for item in sorted(column, key=lambda row: -row["y"]):
                    if not groups or groups[-1][-1]["y"] - item["y"] > 14:
                        groups.append([])
                    groups[-1].append(item)
                entries = []
                for group in groups:
                    entry = ""
                    for item in group:
                        value = item["text"]
                        if entry and re.search(r"[A-Za-z0-9]$", entry) and re.match(r"[A-Za-z]", value):
                            entry += " "
                        entry += value
                    entries.append(entry)
                if columns[index] and entries and entries[0].startswith("("):
                    columns[index][-1] += entries.pop(0)
                columns[index].extend(entries)
    output = ["[PDF 内嵌文字已直接解码；以下内容不是 OCR 猜测]"]
    for index, label in enumerate(labels):
        entries = [entry for entry in columns[index] if not entry.startswith("打印时间:")]
        if entries:
            output.append(f"\n[星期{label}]")
            output.extend(f"- {entry}" for entry in entries)
    return "\n".join(output)


def _extract_unigb_pdf(content):
    if b"/UniGB-UCS2-H" not in content or b"/Encrypt" in content:
        return ""
    pages = []
    for match in re.finditer(rb"\b\d+\s+\d+\s+obj\b(.*?)endobj", content, re.DOTALL):
        body = match.group(1)
        if b"/FlateDecode" not in body or b"stream" not in body:
            continue
        compressed = body.split(b"stream", 1)[1].split(b"endstream", 1)[0]
        compressed = compressed[2:] if compressed.startswith(b"\r\n") else compressed[1:] if compressed.startswith(b"\n") else compressed
        compressed = compressed[:-2] if compressed.endswith(b"\r\n") else compressed[:-1] if compressed.endswith(b"\n") else compressed
        try:
            decoder = zlib.decompressobj()
            decoded = decoder.decompress(compressed, 5_000_000)
            if decoder.unconsumed_tail:
                continue
        except zlib.error:
            continue
        page = _unigb_page(decoded)
        if page:
            pages.append(page)
    return _format_unigb_pages(pages)


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
        [renderer, "-f", "1", "-l", "20", "-r", "300", "-png", str(source), str(prefix)],
        capture_output=True, timeout=120, check=False,
    )
    pages = sorted(directory.glob("ocr-page-*.png"))
    if rendered.returncode or not pages:
        raise HTTPException(422, "无法将扫描版 PDF 转换为图片，文件可能已损坏或加密。")
    page_data = []
    for index, page in enumerate(pages, start=1):
        output = directory / f"ocr-result-{index}"
        result = subprocess.run(
            [tesseract, str(page), str(output), "--tessdata-dir", str(OCR_MODEL_DIR),
             "-l", "+".join(languages), "--psm", "3",
             "-c", "preserve_interword_spaces=1", "-c", "tessedit_create_tsv=1"],
            capture_output=True, timeout=60, check=False,
        )
        tsv = output.with_suffix(".tsv")
        if not result.returncode and tsv.is_file():
            parsed = _read_ocr_tsv(tsv)
            if parsed["words"]:
                page_data.append(parsed)
    text = _format_ocr_pages(page_data).strip()
    if not text:
        raise HTTPException(422, "OCR 没有识别出文字，请确认扫描清晰度或改用更清晰的 PDF。")
    return ("[以下文字由本地 OCR 识别；已尽量保留页面与课表列结构，导入前仍须核对]\n" + text)


def _read_ocr_tsv(path: Path):
    words, width, height = [], 0, 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            try:
                level = int(row.get("level") or 0)
                if level == 1:
                    width, height = int(row["width"]), int(row["height"])
                text = (row.get("text") or "").strip()
                if level != 5 or not text:
                    continue
                words.append({
                    "text": text, "left": int(row["left"]), "top": int(row["top"]),
                    "width": int(row["width"]), "height": int(row["height"]),
                    "block": int(row["block_num"]), "paragraph": int(row["par_num"]),
                    "line": int(row["line_num"]), "confidence": float(row.get("conf") or -1),
                })
            except (KeyError, TypeError, ValueError):
                continue
    return {"width": width, "height": height, "words": words}


def _weekday_layout(page):
    labels = "一二三四五六日"
    candidates = {}
    words = page["words"]
    for word in words:
        compact = re.sub(r"\s+", "", word["text"])
        match = re.search(r"星期([一二三四五六日天])", compact)
        label = match.group(1) if match else None
        center = word["left"] + word["width"] / 2
        bottom = word["top"] + word["height"]
        if compact == "星期":
            nearby = [item for item in words if item is not word
                      and abs(item["top"] - word["top"]) <= max(20, word["height"])
                      and 0 <= item["left"] - (word["left"] + word["width"]) <= 80
                      and item["text"] in labels + "天"]
            if nearby:
                suffix = min(nearby, key=lambda item: item["left"])
                label = suffix["text"]
                center = (word["left"] + suffix["left"] + suffix["width"]) / 2
                bottom = max(bottom, suffix["top"] + suffix["height"])
        if label:
            index = 6 if label == "天" else labels.index(label)
            candidates[index] = (center, bottom)
    if len(candidates) < 3:
        return None
    spacings = [(candidates[b][0] - candidates[a][0]) / (b - a)
                for a in candidates for b in candidates if b > a]
    spacing = median(spacings)
    if spacing <= 0 or spacing < page["width"] * .06 or spacing > page["width"] * .25:
        return None
    origin = median(center - index * spacing for index, (center, _) in candidates.items())
    centers = [origin + index * spacing for index in range(7)]
    bounds = [centers[0] - spacing / 2] + [(centers[i] + centers[i + 1]) / 2 for i in range(6)] + [centers[-1] + spacing / 2]
    return {"centers": centers, "bounds": bounds,
            "header_bottom": max(bottom for _, bottom in candidates.values())}


def _join_ocr_words(words):
    result, previous = "", None
    for word in sorted(words, key=lambda item: item["left"]):
        if previous is not None:
            gap = word["left"] - (previous["left"] + previous["width"])
            if gap > max(8, min(previous["height"], word["height"]) * .45):
                result += " "
        result += word["text"]
        previous = word
    result = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", result)
    return result.strip()


def _ocr_lines(words, page_height, include_position=True):
    groups = {}
    for word in words:
        key = (word["block"], word["paragraph"], word["line"])
        groups.setdefault(key, []).append(word)
    lines = []
    for group in groups.values():
        text = _join_ocr_words(group)
        if text:
            top = min(word["top"] for word in group)
            rendered = f"位置 {top * 100 / max(page_height, 1):05.1f}% | {text}" if include_position else text
            lines.append((top, rendered))
    return [text for _, text in sorted(lines)]


def _format_ocr_pages(pages):
    if not pages:
        return ""
    layout = None
    for page in pages:
        layout = _weekday_layout(page)
        if layout:
            break
    output = []
    if not layout:
        for index, page in enumerate(pages, start=1):
            output.append(f"\n===== 第 {index} 页 =====")
            output.extend(_ocr_lines(page["words"], page["height"], include_position=False))
        return "\n".join(output)
    labels = "一二三四五六日"
    for page_index, page in enumerate(pages, start=1):
        current = _weekday_layout(page)
        active = current or layout
        header_bottom = current["header_bottom"] if current else 0
        output.append(f"\n===== 第 {page_index} 页：课表坐标重建 =====")
        left_words = [word for word in page["words"]
                      if word["top"] >= header_bottom and word["left"] + word["width"] / 2 < active["bounds"][0]]
        if left_words:
            output.append("[时间段与节次]")
            output.extend(_ocr_lines(left_words, page["height"]))
        for day_index, label in enumerate(labels):
            column = [word for word in page["words"] if word["top"] >= header_bottom
                      and active["bounds"][day_index] <= word["left"] + word["width"] / 2 < active["bounds"][day_index + 1]]
            lines = _ocr_lines(column, page["height"])
            if lines:
                output.append(f"[星期{label}]")
                output.extend(lines)
    return "\n".join(output)


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
