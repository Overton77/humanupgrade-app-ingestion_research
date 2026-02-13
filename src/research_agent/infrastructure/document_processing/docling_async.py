from __future__ import annotations

import asyncio
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

import aiohttp

from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat  # PDF, DOCX, HTML, MD, PPTX, XLSX, CSV, IMAGE, etc. :contentReference[oaicite:7]{index=7}


# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------

SourceLike = Union[str, Path]  # URL or local file path
MaybeHeaders = Optional[Dict[str, str]]

# Try docling package exports first; fall back to docling_core
try:
    # Some installs re-export chunkers here
    from docling.chunking import HierarchicalChunker, HybridChunker  # type: ignore
except Exception:  # pragma: no cover
    from docling_core.transforms.chunker import HierarchicalChunker  # type: ignore  # :contentReference[oaicite:8]{index=8}
    from docling_core.transforms.chunker.hybrid_chunker import HybridChunker  # type: ignore


@dataclass(frozen=True)
class DoclingConvertOptions:
    headers: MaybeHeaders = None
    raises_on_error: bool = True
    max_num_pages: int = 10_000_000
    max_file_size: int = 10_000_000_000  # bytes
    # docling expects PageRange if used; keep loosely typed to avoid hard dependency
    page_range: Any = None


@dataclass(frozen=True)
class ExportOptions:
    max_chars: int = 400_000
    markdown_kwargs: Optional[Dict[str, Any]] = None  # e.g. {"strict_text": True}


@dataclass(frozen=True)
class ChunkingConfig:
    """
    mode:
      - "docling_hierarchical": one chunk per structural unit, rich headings metadata
      - "docling_hybrid": hierarchical + token-aware resize/merge (needs tokenizer)
      - "text_chars": simple, deterministic char-based chunking on exported text/markdown
    """
    mode: str = "docling_hierarchical"

    # docling hierarchical knobs (best-effort; docling_core supports these)
    merge_list_items: bool = True
    always_emit_headings: bool = False

    # hybrid knobs
    tokenizer: Any = None               # HuggingFaceTokenizer or OpenAITokenizer wrapper (see docs)
    merge_peers: bool = True

    # text char chunking knobs
    chunk_size: int = 1500
    chunk_overlap: int = 150
    use_markdown: bool = True           # chunk markdown (True) or plain text (False)


@dataclass
class ConvertedArtifact:
    source: str
    input_format: Optional[str]
    doc_name: Optional[str]
    markdown: Optional[str]
    text: Optional[str]
    docling_dict: Optional[Dict[str, Any]]
    meta: Dict[str, Any]
    docling_document: Any


@dataclass
class ChunkArtifact:
    chunk_index: int
    text: str
    # normalized metadata, best-effort across docling/docling_core versions
    meta: Dict[str, Any]


# -----------------------------------------------------------------------------
# Globals: converter + executor
# -----------------------------------------------------------------------------

_CONVERTER: Optional[DocumentConverter] = None
_CONVERTER_LOCK = asyncio.Lock()

_MAX_WORKERS = int(os.getenv("DOCLING_MAX_WORKERS", "2"))
_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS)

_MAX_CONCURRENCY = int(os.getenv("DOCLING_MAX_CONCURRENCY", "2"))
_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENCY)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def is_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https")
    except Exception:
        return False


def guess_input_format_from_name(name: str) -> Optional[InputFormat]:
    n = name.lower().strip()
    if n.endswith((".html", ".htm")):
        return InputFormat.HTML
    if n.endswith((".md", ".markdown")):
        return InputFormat.MD
    if n.endswith(".docx"):
        return InputFormat.DOCX
    if n.endswith(".pptx"):
        return InputFormat.PPTX
    if n.endswith(".xlsx"):
        return InputFormat.XLSX
    if n.endswith(".pdf"):
        return InputFormat.PDF
    if n.endswith(".csv"):
        return InputFormat.CSV
    if re.search(r"\.(png|jpe?g|tiff?|bmp|webp)$", n):
        return InputFormat.IMAGE
    return None


def looks_like_html(text: str) -> bool:
    t = text.lstrip().lower()
    return t.startswith("<!doctype") or t.startswith("<html") or t.startswith("<")


def safe_truncate(s: Optional[str], max_chars: int) -> Optional[str]:
    if s is None:
        return None
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n...[truncated]"


def _pydantic_to_dict(obj: Any) -> Dict[str, Any]:
    # Docling v2 objects are pydantic; support both model_dump() and dict()
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # pydantic v2
    if hasattr(obj, "dict"):
        return obj.dict()  # pydantic v1
    # fallback: best-effort
    return {"repr": repr(obj)}


# -----------------------------------------------------------------------------
# Converter management
# -----------------------------------------------------------------------------

async def get_docling_converter() -> DocumentConverter:
    global _CONVERTER
    if _CONVERTER is not None:
        return _CONVERTER

    async with _CONVERTER_LOCK:
        if _CONVERTER is None:
            _CONVERTER = DocumentConverter()
    return _CONVERTER


# -----------------------------------------------------------------------------
# Fetching (bytes) for URLs when you need it
# -----------------------------------------------------------------------------

async def fetch_url_bytes(
    url: str,
    *,
    headers: MaybeHeaders = None,
    timeout_s: int = 30,
    max_bytes: int = 25_000_000,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Stream-download up to max_bytes.
    """
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    buf = bytearray()

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            final_url = str(resp.url)

            async for chunk in resp.content.iter_chunked(256 * 1024):
                if not chunk:
                    break
                remaining = max_bytes - len(buf)
                if remaining <= 0:
                    break
                buf.extend(chunk[:remaining])

            meta = {
                "status": resp.status,
                "content_type": content_type,
                "final_url": final_url,
                "content_length": resp.headers.get("content-length"),
                "truncated": len(buf) >= max_bytes,
            }
            return bytes(buf), meta


# -----------------------------------------------------------------------------
# Core conversion (async wrappers around Docling sync calls)
# -----------------------------------------------------------------------------

async def convert_source_to_docling(
    source: SourceLike,
    *,
    options: Optional[DoclingConvertOptions] = None,
) -> Any:
    """
    Uses DocumentConverter.convert() which accepts file path or URL. :contentReference[oaicite:9]{index=9}
    """
    options = options or DoclingConvertOptions()
    converter = await get_docling_converter()

    async with _SEMAPHORE:
        def _run() -> Any:
            kwargs: Dict[str, Any] = dict(
                headers=options.headers,
                raises_on_error=options.raises_on_error,
                max_num_pages=options.max_num_pages,
                max_file_size=options.max_file_size,
            )
            if options.page_range is not None:
                kwargs["page_range"] = options.page_range
            return converter.convert(source=str(source), **kwargs)

        return await asyncio.get_running_loop().run_in_executor(_EXECUTOR, _run)


async def convert_string_to_docling(
    content: str,
    *,
    format: InputFormat,
    name: Optional[str] = None,
) -> Any:
    """
    convert_string supports ONLY InputFormat.MD and InputFormat.HTML. :contentReference[oaicite:10]{index=10}
    """
    converter = await get_docling_converter()

    async with _SEMAPHORE:
        def _run() -> Any:
            return converter.convert_string(content=content, format=format, name=name)

        return await asyncio.get_running_loop().run_in_executor(_EXECUTOR, _run)


async def convert_bytes_to_docling(
    data: bytes,
    *,
    filename: str,
    options: Optional[DoclingConvertOptions] = None,
) -> Any:
    """
    Docling.convert expects a path/URL/DocumentStream.
    Easiest: write bytes to temp file, then convert(path).
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


async def convert_webpage(
    url: str,
    *,
    headers: MaybeHeaders = None,
    mode: str = "direct_url",
    options: Optional[DoclingConvertOptions] = None,
) -> Any:
    """
    mode:
      - "direct_url": pass url straight to Docling (fastest, simplest) :contentReference[oaicite:11]{index=11}
      - "fetch_then_string": fetch HTML yourself, then convert_string(HTML) :contentReference[oaicite:12]{index=12}
      - "fetch_then_file": fetch bytes (PDF etc), write temp, then convert
    """
    options = options or DoclingConvertOptions(headers=headers)

    if mode == "direct_url":
        return await convert_source_to_docling(url, options=options)

    raw, meta = await fetch_url_bytes(url, headers=headers)
    ctype = (meta.get("content_type") or "").lower()

    if mode == "fetch_then_string":
        html = raw.decode("utf-8", errors="ignore")
        name = Path(urlparse(url).path).name or "webpage.html"
        return await convert_string_to_docling(html, format=InputFormat.HTML, name=name)

    # fetch_then_file
    name = Path(urlparse(url).path).name or "download.bin"
    return await convert_bytes_to_docling(raw, filename=name, options=options)


# -----------------------------------------------------------------------------
# Export helpers
# -----------------------------------------------------------------------------

def export_docling_markdown(doc: Any, *, opts: ExportOptions) -> str:
    # DoclingDocument.export_to_markdown exists. :contentReference[oaicite:13]{index=13}
    kwargs = opts.markdown_kwargs or {}
    md = doc.export_to_markdown(**kwargs)
    return safe_truncate(md, opts.max_chars) or ""


def export_docling_text(doc: Any, *, opts: ExportOptions) -> str:
    # export_to_text(delim=..., from_element=..., to_element=...) exists. :contentReference[oaicite:14]{index=14}
    txt = doc.export_to_text()
    return safe_truncate(txt, opts.max_chars) or ""


def export_docling_dict(doc: Any) -> Dict[str, Any]:
    # export_to_dict exists. :contentReference[oaicite:15]{index=15}
    return doc.export_to_dict()


# -----------------------------------------------------------------------------
# High-level: convert -> normalized artifact
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
    webpage_mode: str = "direct_url",
) -> ConvertedArtifact:
    """
    One call you can use in ingestion:
      - source: URL/path or bytes
      - returns docling_document plus exports
    """
    export_opts = export_opts or ExportOptions()
    convert_opts = convert_opts or DoclingConvertOptions(headers=headers)

    input_format: Optional[InputFormat] = None
    src_str: str

    if isinstance(source, (str, Path)):
        src_str = str(source)
        input_format = guess_input_format_from_name(src_str)

        if isinstance(source, str) and is_url(source):
            conv_res = await convert_webpage(source, headers=headers, mode=webpage_mode, options=convert_opts)
        else:
            conv_res = await convert_source_to_docling(src_str, options=convert_opts)
    else:
        if not filename:
            filename = "blob.bin"
        src_str = filename
        input_format = guess_input_format_from_name(filename)
        conv_res = await convert_bytes_to_docling(source, filename=filename, options=convert_opts)

    doc = getattr(conv_res, "document", None)
    if doc is None:
        # ConversionResult captures errors when raises_on_error=False. :contentReference[oaicite:16]{index=16}
        raise RuntimeError(f"Docling conversion produced no document. status={getattr(conv_res, 'status', None)}")

    md = export_docling_markdown(doc, opts=export_opts) if export_markdown else None
    txt = export_docling_text(doc, opts=export_opts) if export_text else None
    dct = export_docling_dict(doc) if export_dict else None

    return ConvertedArtifact(
        source=src_str,
        input_format=input_format.name if input_format else None,
        doc_name=getattr(doc, "name", None),
        markdown=md,
        text=txt,
        docling_dict=dct,
        meta={
            "status": str(getattr(conv_res, "status", "")),
            "errors": getattr(conv_res, "errors", None),
            "timings": getattr(conv_res, "timings", None),
            "input": _pydantic_to_dict(getattr(conv_res, "input", None)),
        },
        docling_document=doc,
    )


# -----------------------------------------------------------------------------
# Chunking
# -----------------------------------------------------------------------------

def _char_chunks(text: str, *, chunk_size: int, overlap: int) -> Iterator[Tuple[int, str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap >= chunk_size:
        raise ValueError("chunk_overlap must be < chunk_size")

    start = 0
    ix = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_size)
        yield ix, text[start:end]
        ix += 1
        start = end - overlap


def chunk_docling_document(
    doc: Any,
    *,
    cfg: ChunkingConfig,
    export_opts: Optional[ExportOptions] = None,
) -> List[ChunkArtifact]:
    """
    Returns chunks with metadata.

    - docling_hierarchical: HierarchicalChunker().chunk(doc) :contentReference[oaicite:17]{index=17}
    - docling_hybrid: HybridChunker(tokenizer=...).chunk(doc) :contentReference[oaicite:18]{index=18}
    - text_chars: simple char chunking on markdown/text export
    """
    export_opts = export_opts or ExportOptions()

    mode = cfg.mode.strip().lower()

    if mode == "docling_hierarchical":
        chunker = HierarchicalChunker(
            merge_list_items=cfg.merge_list_items,
            always_emit_headings=cfg.always_emit_headings,
        )
        out: List[ChunkArtifact] = []
        for i, ch in enumerate(chunker.chunk(doc)):
            out.append(
                ChunkArtifact(
                    chunk_index=i,
                    text=getattr(ch, "text", ""),
                    meta=_pydantic_to_dict(getattr(ch, "meta", None)),
                )
            )
        return out

    if mode == "docling_hybrid":
        if cfg.tokenizer is None:
            raise ValueError(
                "docling_hybrid requires cfg.tokenizer. "
                "See Docling hybrid chunking docs for HuggingFace/OpenAI tokenizer wrappers."
            )
        chunker = HybridChunker(
            tokenizer=cfg.tokenizer,
            merge_peers=cfg.merge_peers,
        )
        out: List[ChunkArtifact] = []
        for i, ch in enumerate(chunker.chunk(doc)):
            out.append(
                ChunkArtifact(
                    chunk_index=i,
                    text=getattr(ch, "text", ""),
                    meta=_pydantic_to_dict(getattr(ch, "meta", None)),
                )
            )
        return out

    if mode == "text_chars":
        # Export markdown or text, then chunk deterministically.
        base = export_docling_markdown(doc, opts=export_opts) if cfg.use_markdown else export_docling_text(doc, opts=export_opts)
        out: List[ChunkArtifact] = []
        for i, piece in _char_chunks(base, chunk_size=cfg.chunk_size, overlap=cfg.chunk_overlap):
            out.append(
                ChunkArtifact(
                    chunk_index=i,
                    text=piece,
                    meta={
                        "mode": "text_chars",
                        "chunk_size": cfg.chunk_size,
                        "chunk_overlap": cfg.chunk_overlap,
                        "use_markdown": cfg.use_markdown,
                        "char_start": i * (cfg.chunk_size - cfg.chunk_overlap),
                        "char_end": i * (cfg.chunk_size - cfg.chunk_overlap) + len(piece),
                    },
                )
            )
        return out

    raise ValueError(f"Unknown chunking mode: {cfg.mode}")


# -----------------------------------------------------------------------------
# Async chunk wrapper (if you want chunking off the event loop too)
# -----------------------------------------------------------------------------

async def chunk_docling_document_async(
    doc: Any,
    *,
    cfg: ChunkingConfig,
    export_opts: Optional[ExportOptions] = None,
) -> List[ChunkArtifact]:
    """
    Chunking can be CPU-ish; run it in the executor to avoid blocking the event loop.
    """
    async with _SEMAPHORE:
        def _run() -> List[ChunkArtifact]:
            return chunk_docling_document(doc, cfg=cfg, export_opts=export_opts)

        return await asyncio.get_running_loop().run_in_executor(_EXECUTOR, _run)


# -----------------------------------------------------------------------------
# Batch conversion (async)
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
    webpage_mode: str = "direct_url",
) -> List[ConvertedArtifact]:
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
            webpage_mode=webpage_mode,
        )

    return await asyncio.gather(*[_one(s) for s in sources])


if __name__ == "__main__": 
    async def run_test():  
        artifact = await convert_any_to_artifact(
    "https://www.umgc.edu/current-students/learning-resources/academic-integrity/tutorial/module2/story_content/external_files/CaseStudyExample_annotated--.pdf",
        export_markdown=True,
        export_text=True,
        export_dict=True,
        webpage_mode="direct_url",
        
        )
        doc = artifact.docling_document  



        chunks = await chunk_docling_document_async( 
            doc, 
            cfg=ChunkingConfig(mode="docling_hierarchical", merge_list_items=True)
        ) 

        for chunk in chunks: 
            print("\n\n") 
            print("CHUNK TEXT!!")
            print(chunk.text) 
            print("\n\n")    

            print("CHUNK METADATA!!")
            print(chunk.meta)

    asyncio.run(run_test())
