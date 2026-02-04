#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Dict, Any

# CHANGE THIS IMPORT to match where you put your functions:
# e.g. if you saved your pasted code as docling_helpers.py, use:
# from docling_helpers import (
#     convert_any_to_artifact,
#     convert_webpage,
#     fetch_url_bytes,
#     convert_string_to_docling,
#     export_docling_markdown,
#     export_docling_text,
#     export_docling_dict,
# )
from research_agent.human_upgrade.docling_async import (  # type: ignore
    convert_any_to_artifact,
    convert_webpage,
    fetch_url_bytes,
    convert_string_to_docling,
    export_docling_markdown,
    export_docling_text,
    export_docling_dict,
)

DEFAULT_URLS = [
    # HTML
    "https://www.iana.org/domains/reserved",
    "https://www.rfc-editor.org/rfc/rfc2606.html",
    "https://en.wikipedia.org/wiki/Special-Use_Domain_Name",
    "https://example.com/",
    # PDFs
    "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
    "https://africau.edu/resource/austrategicplan.pdf",
    "https://arxiv.org/pdf/1706.03762v6",
]

def _slugify(url: str) -> str:
    # filename-safe-ish
    return (
        url.replace("https://", "")
        .replace("http://", "")
        .replace("/", "__")
        .replace("?", "_")
        .replace("&", "_")
        .replace("=", "_")
    )[:180]

async def run_one(url: str, out_dir: Path, mode: str) -> Dict[str, Any]:
    """
    mode:
      - direct: pass URL directly to docling (your convert_webpage prefer_direct_url=True)
      - html_string: fetch first; if it's HTML, call convert_string(); else bytes->tempfile->convert()
      - any: use convert_any_to_artifact(url) (DocumentConverter.convert on URL)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    base = _slugify(url)
    meta: Dict[str, Any] = {"url": url, "mode": mode}

    try:
        if mode == "direct":
            conv_res = await convert_webpage(url, prefer_direct_url=True, html_as_string=False)
            doc = getattr(conv_res, "document", None)
            errs = getattr(conv_res, "errors", None)
            meta["errors"] = errs
            if not doc:
                meta["ok"] = False
                return meta

            md = export_docling_markdown(doc)
            txt = export_docling_text(doc)
            dct = export_docling_dict(doc)

        elif mode == "html_string":
            raw, fetch_meta = await fetch_url_bytes(url)
            meta["fetch"] = fetch_meta

            # If it's HTML-ish, use convert_string_to_docling explicitly.
            ctype = (fetch_meta.get("content_type") or "").lower()
            if "text/html" in ctype:
                html = raw.decode("utf-8", errors="ignore")
                conv_res = await convert_string_to_docling(html, name=f"{base}.html")
            else:
                # Let your convert_webpage decide (will likely go bytes->tempfile->convert)
                conv_res = await convert_webpage(url, prefer_direct_url=False, html_as_string=False)

            doc = getattr(conv_res, "document", None)
            errs = getattr(conv_res, "errors", None)
            meta["errors"] = errs
            if not doc:
                meta["ok"] = False
                return meta

            md = export_docling_markdown(doc)
            txt = export_docling_text(doc)
            dct = export_docling_dict(doc)

        elif mode == "any":
            art = await convert_any_to_artifact(url, export_dict=True)
            meta["ok"] = True
            meta["input_format"] = art.input_format
            meta["doc_name"] = art.doc_name
            meta["errors"] = art.meta.get("errors")
            # Write artifact outputs
            (out_dir / f"{base}.md").write_text(art.markdown or "", encoding="utf-8")
            (out_dir / f"{base}.txt").write_text(art.text or "", encoding="utf-8")
            (out_dir / f"{base}.json").write_text(json.dumps(art.docling_dict or {}, indent=2), encoding="utf-8")
            return meta

        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Write outputs for the doc-based modes
        (out_dir / f"{base}.md").write_text(md or "", encoding="utf-8")
        (out_dir / f"{base}.txt").write_text(txt or "", encoding="utf-8")
        (out_dir / f"{base}.json").write_text(json.dumps(dct or {}, indent=2), encoding="utf-8")

        meta["ok"] = True
        meta["doc_name"] = getattr(doc, "name", None)
        meta["md_chars"] = len(md or "")
        meta["txt_chars"] = len(txt or "")
        meta["json_keys"] = len(dct.keys()) if isinstance(dct, dict) else None
        return meta

    except Exception as e:
        meta["ok"] = False
        meta["exception"] = repr(e)
        return meta

async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="out", help="Output directory")
    p.add_argument(
        "--mode",
        default="any",
        choices=["any", "direct", "html_string"],
        help="Conversion route to test",
    )
    p.add_argument("--url", action="append", default=[], help="Add a URL (repeatable)")
    args = p.parse_args()

    urls: List[str] = args.url or DEFAULT_URLS
    out_dir = Path(args.out)

    results = await asyncio.gather(*[run_one(u, out_dir, args.mode) for u in urls])

    # Pretty-ish console summary
    ok = sum(1 for r in results if r.get("ok"))
    print(f"\nDocling smoke test complete: {ok}/{len(results)} OK  (mode={args.mode})")
    for r in results:
        status = "OK " if r.get("ok") else "ERR"
        print(f"- {status}  {r['url']}")
        if not r.get("ok"):
            if r.get("exception"):
                print(f"       exception: {r['exception']}")
            if r.get("errors"):
                print(f"       errors: {r['errors']}")

    # Write machine-readable summary
    (out_dir / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote outputs + summary to: {out_dir.resolve()}\n")

if __name__ == "__main__":
    asyncio.run(main())
