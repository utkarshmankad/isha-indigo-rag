#!/usr/bin/env python3
"""
Airline Policy Web Scraper
Fetches policy pages from Air India, SpiceJet, and DGCA websites.
Structures content as documents and ingests them into the Qdrant KB.

Usage:
    uv run python scripts/scrape_airlines.py --airline air_india
    uv run python scripts/scrape_airlines.py --airline spicejet
    uv run python scripts/scrape_airlines.py --airline dgca
    uv run python scripts/scrape_airlines.py --airline all
    uv run python scripts/scrape_airlines.py --airline all --dry-run

Requires: httpx (already in deps via anthropic/openai transitive)
Optional: beautifulsoup4 (install with: uv add beautifulsoup4)
"""

import argparse
import os
import re
import sys
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

try:
    import httpx
except ImportError:
    print("ERROR: httpx not found. Run: uv add httpx")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("WARNING: beautifulsoup4 not found. Install with: uv add beautifulsoup4")
    print("Falling back to basic text extraction.\n")


# ── Scrape targets ──────────────────────────────────────────────────────────

SCRAPE_TARGETS = {
    "air_india": [
        {
            "url": "https://www.airindia.com/us/en/help-center/baggage.html",
            "id": "AI-SCRAP-BAG",
            "title": "Air India Baggage Help Center (Scraped)",
            "category": "baggage",
            "department": "Ground Operations",
            "doc_type": "policy",
        },
        {
            "url": "https://www.airindia.com/us/en/help-center/cancellation.html",
            "id": "AI-SCRAP-CAN",
            "title": "Air India Cancellations Help Center (Scraped)",
            "category": "cancellations_and_refunds",
            "department": "Revenue Management",
            "doc_type": "policy",
        },
        {
            "url": "https://www.airindia.com/us/en/help-center/check-in.html",
            "id": "AI-SCRAP-CHK",
            "title": "Air India Check-In Help Center (Scraped)",
            "category": "check_in",
            "department": "Ground Operations",
            "doc_type": "procedure",
        },
        {
            "url": "https://www.airindia.com/us/en/travel-information/special-assistance.html",
            "id": "AI-SCRAP-SPC",
            "title": "Air India Special Assistance (Scraped)",
            "category": "special_assistance",
            "department": "Customer Experience",
            "doc_type": "procedure",
        },
    ],
    "spicejet": [
        {
            "url": "https://www.spicejet.com/baggage-information",
            "id": "SJ-SCRAP-BAG",
            "title": "SpiceJet Baggage Information (Scraped)",
            "category": "baggage",
            "department": "Ground Operations",
            "doc_type": "policy",
        },
        {
            "url": "https://www.spicejet.com/cancellation-policy",
            "id": "SJ-SCRAP-CAN",
            "title": "SpiceJet Cancellation Policy (Scraped)",
            "category": "cancellations_and_refunds",
            "department": "Revenue Management",
            "doc_type": "policy",
        },
        {
            "url": "https://www.spicejet.com/checkin-information",
            "id": "SJ-SCRAP-CHK",
            "title": "SpiceJet Check-In Information (Scraped)",
            "category": "check_in",
            "department": "Ground Operations",
            "doc_type": "procedure",
        },
    ],
    "dgca": [
        {
            "url": "https://www.dgca.gov.in/digigov-portal/?page=passenger-rights",
            "id": "DGCA-SCRAP-001",
            "title": "DGCA Passenger Rights (Scraped)",
            "category": "flight_delays_and_cancellations",
            "department": "Regulatory",
            "doc_type": "regulatory",
        },
    ],
}


# ── HTTP fetch ──────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


def fetch_page(url: str, timeout: int = 15) -> str | None:
    """Fetch a URL and return the raw HTML. Returns None on failure."""
    try:
        with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text
    except httpx.HTTPStatusError as e:
        print(f"  HTTP {e.response.status_code} for {url}")
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def extract_text(html: str) -> str:
    """Extract readable text from HTML. Uses BS4 if available, else regex fallback."""
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        # Remove nav, footer, scripts, styles
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        # Find main content area (try common selectors)
        main = (
            soup.find("main")
            or soup.find(id="main-content")
            or soup.find(class_="main-content")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|policy|help|faq", re.I))
            or soup.body
        )
        text = main.get_text(separator="\n") if main else soup.get_text(separator="\n")
    else:
        # Basic regex fallback: strip HTML tags
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&#\d+;", "", text)

    # Clean whitespace
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if len(line) > 30]  # drop short/empty lines
    text = "\n".join(lines)
    # Collapse excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def truncate(text: str, max_chars: int = 3000) -> str:
    """Truncate text to max_chars at a sentence boundary."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_period = cut.rfind(". ")
    if last_period > max_chars // 2:
        cut = cut[:last_period + 1]
    return cut + "\n[content truncated — scraped from website]"


# ── Build document from scraped content ────────────────────────────────────

def scrape_target(target: dict, airline: str) -> dict | None:
    """Fetch a URL, extract text, and return a document dict."""
    url = target["url"]
    print(f"  Fetching: {url}")
    html = fetch_page(url)
    if html is None:
        print(f"  SKIP: Could not fetch {url}")
        return None

    text = extract_text(html)
    if len(text) < 200:
        print(f"  SKIP: Extracted text too short ({len(text)} chars) — likely JS-rendered page")
        return None

    content = truncate(text)
    print(f"  OK: {len(content)} chars extracted")

    return {
        "id": target["id"],
        "airline": airline,
        "title": target["title"],
        "category": target["category"],
        "department": target["department"],
        "doc_type": target["doc_type"],
        "last_updated": date.today().isoformat(),
        "content": content,
    }


# ── Ingest into Qdrant ──────────────────────────────────────────────────────

def ingest_documents(documents: list[dict]) -> None:
    """Embed and upsert documents into the Qdrant airline_kb collection."""
    from src.embedding.embedder import embed_chunks
    from src.embedding.vector_store import QdrantVectorStore
    from src.ingestion.chunker import ingest_all

    store = QdrantVectorStore()
    chunks = ingest_all(documents)
    if not chunks:
        print("No chunks produced — nothing to ingest.")
        return
    embedded = embed_chunks(chunks)
    store.upsert(embedded)
    stats = store.stats()
    print(f"\nQdrant collection now has {stats['total_vectors']} total vectors.")


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape airline websites and ingest into Qdrant.")
    parser.add_argument(
        "--airline",
        choices=["all", "air_india", "spicejet", "dgca"],
        default="all",
        help="Which airline's pages to scrape.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and print content without ingesting into Qdrant.",
    )
    args = parser.parse_args()

    airlines_to_scrape = (
        list(SCRAPE_TARGETS.keys())
        if args.airline == "all"
        else [args.airline]
    )

    all_documents: list[dict] = []

    for airline in airlines_to_scrape:
        targets = SCRAPE_TARGETS.get(airline, [])
        print(f"\n{'='*60}")
        print(f"Scraping: {airline} ({len(targets)} pages)")
        print("=" * 60)

        for target in targets:
            doc = scrape_target(target, airline)
            if doc:
                all_documents.append(doc)
            time.sleep(1.5)  # be polite to servers

    print(f"\n{'='*60}")
    print(f"Scraped {len(all_documents)} documents successfully.")

    if args.dry_run:
        print("\n[dry-run] Not ingesting. Document previews:")
        for doc in all_documents:
            print(f"\n  [{doc['id']}] {doc['title']}")
            print(f"  Airline: {doc['airline']} | Category: {doc['category']}")
            print(f"  Content preview: {doc['content'][:200].replace(chr(10), ' ')}")
        return

    if not all_documents:
        print("No documents scraped — nothing to ingest.")
        return

    print(f"\nIngesting {len(all_documents)} scraped documents into Qdrant...")
    ingest_documents(all_documents)
    print("Done.")


if __name__ == "__main__":
    main()
