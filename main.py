import os, json, asyncio
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
from inscriptis import get_text
import tiktoken

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Env vars
SERPER_API_KEY      = os.getenv("SERPER_API_KEY", "")
SCRAPER_AUTH_HEADER = os.getenv("SCRAPER_AUTH_HEADER", "")

SERPER_HEADERS  = {"X-API-KEY": SERPER_API_KEY,     "Content-Type": "application/json"}
SCRAPER_HEADERS = {"accept": "application/json", "content-type": "application/json", "authorization": SCRAPER_AUTH_HEADER}

SEARCH_URL      = "https://google.serper.dev/search"
SCRAPER_API_URL = "https://scraper-api.decodo.com/v2/scrape"

STAR_DIVIDER   = "*" * 100
DASH_DIVIDER   = "-" * 100
MAX_TOKENS_PER_PAGE = 2500
encoding       = tiktoken.encoding_for_model("gpt-4o-mini")

async def get_search_results(q: str, client: httpx.AsyncClient) -> dict:
    try:
        r = await client.post(SEARCH_URL, headers=SERPER_HEADERS, json={"q": q})
        r.raise_for_status()
        return r.json()
    except:
        return {}

async def fetch_html(url: str, client: httpx.AsyncClient) -> str:
    try:
        r = await client.post(SCRAPER_API_URL, headers=SCRAPER_HEADERS, json={"url": url}, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [{}])[0].get("content", "") or ""
    except:
        return ""

def truncate_tokens(text: str, limit: int) -> str:
    try:
        toks = encoding.encode(text)
        return text if len(toks) <= limit else encoding.decode(toks[:limit]) + "..."
    except:
        return ""

def convert_and_truncate(html: str) -> str:
    try:
        plain = get_text(html)
        return truncate_tokens(plain, MAX_TOKENS_PER_PAGE)
    except:
        return ""

@app.get("/search-and-extract/")
async def search_and_extract(query: str = Query(..., description="Search query")):
    async with httpx.AsyncClient() as client:
        sj = await get_search_results(query, client)
        organic = sj.get("organic", [])[:3]
        urls = [e.get("link","") for e in organic if e.get("link")]
        if not urls:
            return {"text": "No results found."}

        htmls = await asyncio.gather(*(fetch_html(u, client) for u in urls))
        contents = [convert_and_truncate(h) for h in htmls]

        blocks = []
        for i, (u, c) in enumerate(zip(urls, contents), start=1):
            blocks.append(
                f"{DASH_DIVIDER}\n"
                f"{i}. {u}\n"
                f"{DASH_DIVIDER}\n"
                f"{c.strip()}\n"
            )

        output = (
            f"{STAR_DIVIDER}\n"
            f"SEARCH RESULTS PAGE FOR QUERY: \"{query}\"\n"
            f"{STAR_DIVIDER}\n"
            f"{json.dumps(sj, indent=2)}\n\n"
            f"{STAR_DIVIDER}\n"
            f"FETCHED CONTENT FOR TOP 3 SEARCH RESULTS\n"
            f"{STAR_DIVIDER}\n"
            + "".join(blocks)
        )
        return {"text": output}
