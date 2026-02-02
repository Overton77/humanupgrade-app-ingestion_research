from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

import aiohttp

# Docling (sync library; we wrap it async)
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat  # includes PDF, DOCX, HTML, MD, XLSX, PPTX, CSV, IMAGE, etc.


# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------

SourceLike = Union[str, Path]  # URL or local file path
MaybeHeaders = Optional[Dict[str, str]]


@dataclass(frozen=True)
class DoclingConvertOptions:
    # These map directly to DocumentConverter.convert(...) args.
    headers: MaybeHeaders = None
    raises_on_error: bool = True
    max_num_pages: int = 10_000_000
    max_file_size: int = 10_000_000_000  # bytes
    # page_range exists in Docling but keeping this optional to avoid tight coupling.
    page_range: Any = None  # pass docling.datamodel.page_range.PageRange if you use it


@dataclass(frozen=True)
class ExportOptions:
    max_chars: int = 200_000
    # If you want "plain text without markdown markers", Docling has export_to_text();
    # export_to_markdown(strict_text=True) is also used in CLI patterns, but export_to_text exists too.
    markdown_strict_text: bool = False


@dataclass
class ConvertedArtifact:
    """Normalized result envelope for downstream ingestion."""
    source: str  # url or file path (stringified)
    input_format: Optional[str]  # e.g. "PDF", "DOCX", "HTML"
    doc_name: Optional[str]
    markdown: Optional[str]
    text: Optional[str]
    docling_dict: Optional[Dict[str, Any]]
    meta: Dict[str, Any]


# -----------------------------------------------------------------------------
# Globals: converter + executor
# -----------------------------------------------------------------------------

_CONVERTER: Optional[DocumentConverter] = None
_CONVERTER_LOCK = asyncio.Lock()

# Docling conversion can be CPU-heavy; keep this modest by default.
# You can tune via env var DOCLING_MAX_WORKERS.
_MAX_WORKERS = int(os.getenv("DOCLING_MAX_WORKERS", "2"))
_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS)

# Limit concurrent conversions (also tuneable)
_MAX_CONCURRENCY = int(os.getenv("DOCLING_MAX_CONCURRENCY", "2"))
_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENCY)


# -----------------------------------------------------------------------------
# Converter management
# -----------------------------------------------------------------------------

async def get_docling_converter() -> DocumentConverter:
    """
    Lazy-init a singleton DocumentConverter.
    This is usually what you want so models/pipelines are reused across calls.
    """
    global _CONVERTER
    if _CONVERTER is not None:
        return _CONVERTER

    async with _CONVERTER_LOCK:
        if _CONVERTER is None:
            # You can pass allowed_formats / format_options here if you want to lock it down.
            _CONVERTER = DocumentConverter()
    return _CONVERTER


# -----------------------------------------------------------------------------
# URL / format helpers
# -----------------------------------------------------------------------------

def is_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https")
    except Exception:
        return False


def guess_input_format_from_name(name: str) -> Optional[InputFormat]:
    """
    Guess Docling InputFormat from extension or basic heuristics.
    Docling also auto-detects formats, so this is mostly for convert_string routing.
    """
    n = name.lower().strip()

    # HTML / MD as strings
    if n.endswith(".html") or n.endswith(".htm"):
        return InputFormat.HTML
    if n.endswith(".md") or n.endswith(".markdown"):
        return InputFormat.MD

    # Office
    if n.endswith(".docx"):
        return InputFormat.DOCX
    if n.endswith(".pptx"):
        return InputFormat.PPTX
    if n.endswith(".xlsx"):
        return InputFormat.XLSX

    # Other
    if n.endswith(".pdf"):
        return InputFormat.PDF
    if n.endswith(".csv"):
        return InputFormat.CSV
    if n.endswith(".vtt"):
        return InputFormat.VTT
    if n.endswith(".json"):
        return InputFormat.JSON_DOCLING

    # images
    if re.search(r"\.(png|jpe?g|tiff?|bmp|webp)$", n):
        return InputFormat.IMAGE

    return None


def looks_like_html(text: str) -> bool:
    t = text.lstrip()
    return t.startswith("<!doctype") or t.startswith("<html") or t.startswith("<")


def looks_like_markdown(text: str) -> bool:
    # heuristic: headings/lists/links
    return bool(re.search(r"(^#\s)|(\[[^\]]+\]\([^)]+\))|(^-\s)|(^\*\s)", text, re.M))


def safe_truncate(s: Optional[str], max_chars: int) -> Optional[str]:
    if s is None:
        return None
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n...[truncated]"


# -----------------------------------------------------------------------------
# Core conversion (async wrappers around Docling sync calls)
# -----------------------------------------------------------------------------

async def convert_source_to_docling(
    source: SourceLike,
    *,
    options: Optional[DoclingConvertOptions] = None,
) -> Any:
    """
    Convert a URL or local file path using DocumentConverter.convert().

    Docling's convert() supports file path, URL, or DocumentStream (we use path/url here). :contentReference[oaicite:4]{index=4}
    """
    options = options or DoclingConvertOptions()
    converter = await get_docling_converter()

    async with _SEMAPHORE:
        def _run_convert() -> Any:
            kwargs: Dict[str, Any] = dict(
                headers=options.headers,
                raises_on_error=options.raises_on_error,
                max_num_pages=options.max_num_pages,
                max_file_size=options.max_file_size,
            )
            if options.page_range is not None:
                kwargs["page_range"] = options.page_range
            return converter.convert(str(source), **kwargs)

        return await asyncio.get_running_loop().run_in_executor(_EXECUTOR, _run_convert)


async def convert_string_to_docling(
    content: str,
    *,
    format: Optional[InputFormat] = None,
    name: Optional[str] = None,
) -> Any:
    """
    Convert HTML/Markdown content provided as a string via convert_string().
    Only MD and HTML are supported by convert_string(). :contentReference[oaicite:5]{index=5}
    """
    converter = await get_docling_converter()

    if format is None:
        if looks_like_html(content):
            format = InputFormat.HTML
        elif looks_like_markdown(content):
            format = InputFormat.MD
        else:
            # default to HTML because many web captures are HTML-ish
            format = InputFormat.HTML

    async with _SEMAPHORE:
        def _run_convert_string() -> Any:
            return converter.convert_string(content=content, format=format, name=name)

        return await asyncio.get_running_loop().run_in_executor(_EXECUTOR, _run_convert_string)


async def convert_bytes_to_docling(
    data: bytes,
    *,
    filename: str,
    options: Optional[DoclingConvertOptions] = None,
) -> Any:
    """
    Convert bytes by writing to a temp file then using convert(path).
    (This avoids depending on DocumentStream import paths.)
    """
    options = options or DoclingConvertOptions()
    suffix = Path(filename).suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        tmp_path = f.name
        f.write(data)

    try:
        return await convert_source_to_docling(tmp_path, options=options)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# -----------------------------------------------------------------------------
# Webpage helpers
# -----------------------------------------------------------------------------

async def fetch_url_bytes(
    url: str,
    *,
    headers: MaybeHeaders = None,
    timeout_s: int = 30,
    max_bytes: int = 15_000_000,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Fetch raw bytes from a URL (HTML/PDF/etc). Useful when:
      - you need custom headers/cookies
      - you want to store a copy
      - you want to run convert_string for HTML
    """
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            raw = await resp.content.readexactly(min(resp.content_length or max_bytes, max_bytes)) \
                if resp.content_length and resp.content_length > max_bytes \
                else await resp.read()

            if len(raw) > max_bytes:
                raw = raw[:max_bytes]

            meta = {
                "status": resp.status,
                "content_type": content_type,
                "final_url": str(resp.url),
                "content_length": resp.headers.get("content-length"),
            }
            return raw, meta


async def convert_webpage(
    url: str,
    *,
    headers: MaybeHeaders = None,
    prefer_direct_url: bool = True,
    html_as_string: bool = False,
    options: Optional[DoclingConvertOptions] = None,
) -> Any:
    """
    Convert a webpage. You have two modes:

    1) prefer_direct_url=True (default): pass the URL directly to Docling convert().
       Docling supports URL sources. :contentReference[oaicite:6]{index=6}

    2) html_as_string=True: fetch HTML yourself (useful if you already have rendered HTML)
       and call convert_string(InputFormat.HTML). :contentReference[oaicite:7]{index=7}
    """
    options = options or DoclingConvertOptions(headers=headers)

    if prefer_direct_url and not html_as_string:
        return await convert_source_to_docling(url, options=options)

    raw, meta = await fetch_url_bytes(url, headers=headers)
    # decide if it looks like HTML; if not, feed bytes as a file
    ctype = (meta.get("content_type") or "").lower()

    if "text/html" in ctype or looks_like_html(raw.decode("utf-8", errors="ignore")):
        html = raw.decode("utf-8", errors="ignore")
        # Name helps Docling attach a file extension
        name = Path(urlparse(url).path).name or "webpage.html"
        return await convert_string_to_docling(html, format=InputFormat.HTML, name=name)
    else:
        # probably a PDF or something else; keep filename suffix if present
        name = Path(urlparse(url).path).name or "download.bin"
        return await convert_bytes_to_docling(raw, filename=name, options=options)


# -----------------------------------------------------------------------------
# Export helpers (DoclingDocument -> useful strings / dict)
# -----------------------------------------------------------------------------

def export_docling_markdown(doc: Any, *, opts: Optional[ExportOptions] = None) -> str:
    """
    Export DoclingDocument to Markdown. :contentReference[oaicite:8]{index=8}
    """
    opts = opts or ExportOptions()
    md = doc.export_to_markdown(strict_text=opts.markdown_strict_text)
    return safe_truncate(md, opts.max_chars) or ""


def export_docling_text(doc: Any, *, opts: Optional[ExportOptions] = None) -> str:
    """
    Export DoclingDocument to plain-ish text using export_to_text(). :contentReference[oaicite:9]{index=9}
    """
    opts = opts or ExportOptions()
    txt = doc.export_to_text()
    return safe_truncate(txt, opts.max_chars) or ""


def export_docling_dict(doc: Any) -> Dict[str, Any]:
    """
    Lossless structured export to dict. :contentReference[oaicite:10]{index=10}
    """
    return doc.export_to_dict()


def save_docling_json(
    doc: Any,
    *,
    out_path: Union[str, Path],
    image_mode: Optional[Any] = None,
) -> str:
    """
    Save lossless Docling JSON to disk. DoclingDocument.save_as_json() exists. :contentReference[oaicite:11]{index=11}
    """
    out_path = str(out_path)
    if image_mode is None:
        doc.save_as_json(filename=out_path)
    else:
        doc.save_as_json(filename=out_path, image_mode=image_mode)
    return out_path


# -----------------------------------------------------------------------------
# High-level convenience: convert -> return normalized artifact
# -----------------------------------------------------------------------------

async def convert_any_to_artifact(
    source: Union[SourceLike, bytes],
    *,
    filename: Optional[str] = None,
    headers: MaybeHeaders = None,
    export_markdown: bool = True,
    export_text: bool = True,
    export_dict: bool = True,
    export_opts: Optional[ExportOptions] = None,
    convert_opts: Optional[DoclingConvertOptions] = None,
) -> ConvertedArtifact:
    """
    One call for ingestion pipelines:
    - Converts input to a DoclingDocument
    - Exports markdown/text/dict as requested
    - Returns a normalized envelope
    """
    export_opts = export_opts or ExportOptions()
    convert_opts = convert_opts or DoclingConvertOptions(headers=headers)

    input_format: Optional[InputFormat] = None
    src_str: str

    if isinstance(source, (str, Path)):
        src_str = str(source)
        input_format = guess_input_format_from_name(src_str)
        conv_res = await convert_source_to_docling(src_str, options=convert_opts)
    else:
        # bytes
        if not filename:
            filename = "blob.bin"
        src_str = filename
        input_format = guess_input_format_from_name(filename)
        conv_res = await convert_bytes_to_docling(source, filename=filename, options=convert_opts)

    doc = getattr(conv_res, "document", None)
    errors = getattr(conv_res, "errors", None)

    md = export_docling_markdown(doc, opts=export_opts) if (doc and export_markdown) else None
    txt = export_docling_text(doc, opts=export_opts) if (doc and export_text) else None
    dct = export_docling_dict(doc) if (doc and export_dict) else None

    return ConvertedArtifact(
        source=src_str,
        input_format=input_format.name if input_format else None,
        doc_name=getattr(doc, "name", None) if doc else None,
        markdown=md,
        text=txt,
        docling_dict=dct,
        meta={
            "status": str(getattr(conv_res, "status", "")),
            "errors": errors,
            "timings": getattr(conv_res, "timings", None),
            "version": getattr(conv_res, "version", None),
        },
    )


# -----------------------------------------------------------------------------
# Batch conversion helpers
# -----------------------------------------------------------------------------

async def convert_many_to_artifacts(
    sources: Sequence[SourceLike],
    *,
    headers: MaybeHeaders = None,
    export_markdown: bool = True,
    export_text: bool = True,
    export_dict: bool = False,
    export_opts: Optional[ExportOptions] = None,
    convert_opts: Optional[DoclingConvertOptions] = None,
) -> List[ConvertedArtifact]:
    """
    Async batch conversion with concurrency limits.
    Prefer this over DocumentConverter.convert_all() when you want asyncio-native flow control.
    """
    export_opts = export_opts or ExportOptions()
    convert_opts = convert_opts or DoclingConvertOptions(headers=headers)

    async def _one(s: SourceLike) -> ConvertedArtifact:
        return await convert_any_to_artifact(
            s,
            headers=headers,
            export_markdown=export_markdown,
            export_text=export_text,
            export_dict=export_dict,
            export_opts=export_opts,
            convert_opts=convert_opts,
        )

    return await asyncio.gather(*[_one(s) for s in sources])
