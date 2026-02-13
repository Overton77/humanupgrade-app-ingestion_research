#!/usr/bin/env python
import asyncio
import os
import sys
from typing import List

# 🔧 Adjust this import path if needed
from research_agent.tools.medical_db_tools.pub_med_tools import (
    get_http_session,
    pubmed_esearch,
    format_pubmed_esearch,
    pubmed_esummary,
    format_pubmed_esummary,
    pubmed_efetch_abstracts,
    format_pubmed_efetch_abstracts,
    pmc_esearch,
    format_pmc_esearch,
    pmc_efetch_fulltext_xml,
    format_pmc_efetch_fulltext_xml,
    pubmed_search_summarizable_chunk,
    close_http_session,
)


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


async def run_pubmed_flow(term: str, max_results: int = 5) -> None:
    """
    Run all low-level PubMed/PMC helper functions and print the exact raw +
    formatted outputs, so you can see what your LLM tools are getting.
    """
    api_key = os.getenv("NCBI_API_KEY")
    email = os.getenv("NCBI_EMAIL")  # optional but nice to set

    session = await get_http_session()

    # ------------------------------------------------------------------
    # 1) PubMed ESearch (JSON) + formatted
    # ------------------------------------------------------------------
    _print_header(f"1) pubmed_esearch(term={term!r})")
    es = await pubmed_esearch(
        session=session,
        term=term,
        retmax=max_results,
        api_key=api_key,
        email=email,
    )
    print("Raw ESearch JSON keys:", list(es.keys()))
    print("Raw esearchresult keys:", list(es.get("esearchresult", {}).keys()))
    print("Raw idlist:", es.get("esearchresult", {}).get("idlist"))

    es_formatted = format_pubmed_esearch(es, max_ids=max_results)
    _print_header("1a) format_pubmed_esearch(...)")
    print(es_formatted)

    pmids: List[str] = (es.get("esearchresult", {}).get("idlist") or [])[:max_results]
    if not pmids:
        print("\n⚠️ No PMIDs returned – stopping PubMed part early.")
    else:
        # ------------------------------------------------------------------
        # 2) PubMed ESummary (JSON) + formatted
        # ------------------------------------------------------------------
        _print_header(f"2) pubmed_esummary(ids={pmids})")
        esum = await pubmed_esummary(
            session=session,
            ids=pmids,
            api_key=api_key,
            email=email,
        )
        print("Raw ESummary JSON top-level keys:", list(esum.keys()))
        result_block = esum.get("result", {})
        print("Raw ESummary 'result' keys:", list(result_block.keys())[:20])

        esum_formatted = format_pubmed_esummary(esum, max_articles=max_results)
        _print_header("2a) format_pubmed_esummary(...)")
        print(esum_formatted)

        # ------------------------------------------------------------------
        # 3) PubMed EFetch abstracts (text) + formatted
        # ------------------------------------------------------------------
        _print_header(f"3) pubmed_efetch_abstracts(ids={pmids})")
        abstracts_text = await pubmed_efetch_abstracts(
            session=session,
            ids=pmids,
            api_key=api_key,
            email=email,
        )
        print(f"Raw abstracts_text length: {len(abstracts_text)}")
        print("First 800 chars of raw abstracts_text:\n")
        print(abstracts_text[:800])

        abstracts_formatted = format_pubmed_efetch_abstracts(
            pmids=pmids,
            abstracts_text=abstracts_text,
            max_chars=2000,
        )
        _print_header("3a) format_pubmed_efetch_abstracts(...)")
        print(abstracts_formatted)

    # ----------------------------------------------------------------------
    # 4) High-level PubMed summarizable chunk (what you feed into summarize)
    # ----------------------------------------------------------------------
    _print_header(f"4) pubmed_search_summarizable_chunk(term={term!r})")
    chunk = await pubmed_search_summarizable_chunk(
        session=session,
        term=term,
        max_results=max_results,
    )
    print(f"Chunk type: {type(chunk)}")
    print(f"Total chunk length: {len(chunk)} characters\n")
    print("First 1200 chars of chunk:\n")
    print(chunk[:1200])

    # ----------------------------------------------------------------------
    # 5) PMC ESearch + EFetch fulltext XML (for completeness)
    # ----------------------------------------------------------------------
    _print_header(f"5) pmc_esearch(term={term!r})")
    pmc_es = await pmc_esearch(
        session=session,
        term=term,
        retmax=max_results,
        api_key=api_key,
        email=email,
    )
    print("Raw PMC ESearch keys:", list(pmc_es.keys()))
    print("Raw PMC esearchresult keys:", list(pmc_es.get("esearchresult", {}).keys()))
    pmc_ids: List[str] = (pmc_es.get("esearchresult", {}).get("idlist") or [])[:max_results]
    print("PMC idlist:", pmc_ids)

    pmc_es_formatted = format_pmc_esearch(pmc_es, max_ids=max_results)
    _print_header("5a) format_pmc_esearch(...)")
    print(pmc_es_formatted)

    if pmc_ids:
        _print_header(f"6) pmc_efetch_fulltext_xml(ids={pmc_ids})")
        pmc_xml = await pmc_efetch_fulltext_xml(
            session=session,
            ids=pmc_ids,
            api_key=api_key,
            email=email,
        )
        print(f"Raw PMC XML length: {len(pmc_xml)}")
        print("First 800 chars of raw XML:\n")
        print(pmc_xml[:800])

        pmc_fulltext_formatted = format_pmc_efetch_fulltext_xml(
            pmc_ids=pmc_ids,
            xml_text=pmc_xml,
            max_chars=4000,
        )
        _print_header("6a) format_pmc_efetch_fulltext_xml(...)")
        print(pmc_fulltext_formatted)
    else:
        print("\n⚠️ No PMC IDs returned – skipping pmc_efetch_fulltext_xml.")

    # NOTE: we intentionally do NOT call pubmed_literature_search_tool here,
    # this script is only for inspecting the raw helper outputs.


async def amain() -> None:
    if len(sys.argv) > 1:
        term = " ".join(sys.argv[1:])
    else:
        # Default query you can change freely
        term = "spermidine longevity human trial"

    print(f"🔍 Running PubMed/PMC test flow for term: {term!r}") 
    try: 
        await run_pubmed_flow(term)
    finally: 
        await close_http_session()
        print("\n✅ HTTP session closed")


if __name__ == "__main__":
    asyncio.run(amain())
