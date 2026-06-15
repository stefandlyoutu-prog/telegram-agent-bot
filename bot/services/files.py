import io
import re
from html.parser import HTMLParser

from aiogram import Bot

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_TEXT_CHARS = 80_000

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".html", ".htm", ".json", ".xml",
    ".csv", ".py", ".js", ".ts", ".css", ".yaml", ".yml", ".ini",
    ".log", ".rtf", ".tex", ".sql", ".sh", ".bash", ".env",
}
PDF_EXTENSIONS = {".pdf"}
DOCX_EXTENSIONS = {".docx"}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def get_text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self.parts))


class FileError(Exception):
    pass


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise FileError("Не удалось прочитать текстовую кодировку файла")


def _html_to_text(raw: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw)
    return parser.get_text().strip()


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _extract_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()


def extract_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise FileError(f"Файл больше {MAX_FILE_BYTES // (1024*1024)} MB")

    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in TEXT_EXTENSIONS | PDF_EXTENSIONS | DOCX_EXTENSIONS:
        raise FileError(
            f"Формат {ext or 'без расширения'} не поддержан.\n"
            "Можно: txt, md, html, pdf, docx, json, py и др."
        )

    if ext in PDF_EXTENSIONS:
        text = _extract_pdf(data)
    elif ext in DOCX_EXTENSIONS:
        text = _extract_docx(data)
    else:
        raw = _decode_text(data)
        text = _html_to_text(raw) if ext in {".html", ".htm"} else raw

    text = text.strip()
    if not text:
        raise FileError("В файле не найден текст (пустой или только картинки)")

    if len(text) > MAX_TEXT_CHARS:
        text = (
            text[:MAX_TEXT_CHARS]
            + f"\n\n[… обрезано: показаны первые {MAX_TEXT_CHARS} символов]"
        )
    return text


async def download_document(bot: Bot, file_id: str) -> bytes:
    from bot.services.telegram_net import format_telegram_error, telegram_retry

    try:
        file = await telegram_retry("get_file", lambda: bot.get_file(file_id))
    except Exception as e:
        raise FileError(format_telegram_error(e)) from e

    if file.file_size and file.file_size > MAX_FILE_BYTES:
        raise FileError(f"Файл больше {MAX_FILE_BYTES // (1024*1024)} MB")
    buf = io.BytesIO()
    try:
        await telegram_retry(
            "download_file",
            lambda: bot.download_file(file.file_path, buf),
        )
    except Exception as e:
        raise FileError(format_telegram_error(e)) from e
    return buf.getvalue()
