import aiohttp
from typing import Sequence, Optional, Dict, Any, List 
import json  
from dotenv import load_dotenv 

load_dotenv()  

NCBI_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# NCBI strongly recommends providing email + tool, and using an API key
# if you go >3 req/s. :contentReference[oaicite:1]{index=1}
DEFAULT_TOOL = "human-upgrade-app"


async def _eutils_get(
    session: aiohttp.ClientSession,
    util: str,                    # "esearch", "esummary", "efetch", ...
    params: Dict[str, Any],
) -> str:
    url = f"{NCBI_BASE_URL}/{util}.fcgi"
    async with session.get(url, params=params, timeout=30) as resp:
        resp.raise_for_status()
        return await resp.text()   # caller can decide to parse JSON or XML 


import json

async def pubmed_esearch(
    session: aiohttp.ClientSession,
    term: str,
    retmax: int = 50,
    api_key: Optional[str] = None,
    email: Optional[str] = None,
    use_history: bool = False,   # if True, use WebEnv/QueryKey (for huge result sets)
) -> Dict[str, Any]:
    params = {
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retmax": retmax,
        "tool": DEFAULT_TOOL,
    }
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    if use_history:
        params["usehistory"] = "y"

    text = await _eutils_get(session, "esearch", params)
    return json.loads(text)


async def pubmed_esummary(
    session: aiohttp.ClientSession,
    ids: Sequence[str],
    api_key: Optional[str] = None,
    email: Optional[str] = None,
) -> Dict[str, Any]:
    if not ids:
        return {}
    params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "json",
        "tool": DEFAULT_TOOL,
    }
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key

    text = await _eutils_get(session, "esummary", params)
    return json.loads(text)


async def pubmed_efetch_abstracts(
    session: aiohttp.ClientSession,
    ids: Sequence[str],
    api_key: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    """
    Returns plain-text abstracts concatenated together (PubMed EFetch).
    You can split on '\n\n' or parse further if needed.
    """
    if not ids:
        return ""

    params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "rettype": "abstract",
        "retmode": "text",  # text abstracts; you can also use xml
        "tool": DEFAULT_TOOL,
    }
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key

    return await _eutils_get(session, "efetch", params)


async def pmc_esearch(
    session: aiohttp.ClientSession,
    term: str,
    retmax: int = 50,
    api_key: Optional[str] = None,
    email: Optional[str] = None,
    use_history: bool = False,
) -> Dict[str, Any]:
    params = {
        "db": "pmc",
        "term": term,
        "retmode": "json",
        "retmax": retmax,
        "tool": DEFAULT_TOOL,
    }
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    if use_history:
        params["usehistory"] = "y"

    text = await _eutils_get(session, "esearch", params)
    import json
    return json.loads(text)


async def pmc_efetch_fulltext_xml(
    session: aiohttp.ClientSession,
    ids: Sequence[str],     # e.g. ["PMC1234567", "PMC7654321"]
    api_key: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    if not ids:
        return ""

    params = {
        "db": "pmc",
        "id": ",".join(ids),
        "rettype": "full",
        "retmode": "xml",
        "tool": DEFAULT_TOOL,
    }
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key

    return await _eutils_get(session, "efetch", params)
