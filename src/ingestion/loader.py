from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from src.config import AppConfig
from src.registry import Source, SourceRegistry

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
TRACKING_PARAMS = {"fbclid", "gclid", "gclsrc", "dclid", "msclkid"}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def normalize_url(url: str) -> str:
    """Canonicalize a URL for strict allowlist comparison."""
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return url.strip()

    netloc = parsed.netloc.lower()
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    path = parsed.path.rstrip("/") or "/"
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_PARAMS:
            continue
        query_items.append((lowered, value))

    return urlunsplit((scheme, netloc, path, urlencode(sorted(query_items)), ""))


def normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        if line:
            cleaned.append(line)
            blank_run = 0
        else:
            blank_run += 1
            if blank_run == 1:
                cleaned.append("")
    return "\n".join(cleaned).strip()


def extract_page(html: str) -> dict:
    """Extract readable content. No anchors are inspected for link discovery."""
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("title") or soup.find("h1")
    title = title_tag.get_text(" ", strip=True) if title_tag else ""

    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    root = soup.find("main") or soup.body or soup

    headings = [
        heading.get_text(" ", strip=True)
        for heading in root.find_all(["h1", "h2", "h3", "h4"])
    ]

    tables: list[str] = []
    for table in root.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [
                cell.get_text(" ", strip=True)
                for cell in tr.find_all(["th", "td"])
            ]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            tables.append("\n".join(rows))

    lists = [
        item.get_text(" ", strip=True)
        for item in root.find_all("li")
        if item.get_text(" ", strip=True)
    ]

    text = normalize_text(root.get_text("\n", strip=True))
    return {
        "title": title,
        "text": text,
        "structure": {
            "headings": [value for value in headings if value],
            "tables": tables,
            "lists": lists,
        },
    }


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def make_allowlist_hook(allowed: set[str]):
    """Last-resort guard: fail before sending any out-of-allowlist request."""
    def hook(request: httpx.Request) -> None:
        if normalize_url(str(request.url)) not in allowed:
            raise RuntimeError(f"Blocked out-of-allowlist request: {request.url}")

    return hook


def fetch_allowed(
    client: httpx.Client,
    start_url: str,
    allowed: set[str],
    max_redirects: int = 2,
) -> httpx.Response:
    current = start_url
    for _ in range(max_redirects + 1):
        if normalize_url(current) not in allowed:
            raise RuntimeError(f"Blocked request outside allowlist: {current}")

        response = client.get(current)
        if response.status_code in REDIRECT_STATUSES:
            location = response.headers.get("location")
            if not location:
                raise ValueError(f"Redirect without Location header: {current}")
            target = urljoin(current, location)
            if normalize_url(target) not in allowed:
                raise RuntimeError(f"Blocked redirect outside allowlist: {target}")
            current = target
            continue

        response.raise_for_status()
        if normalize_url(str(response.url)) not in allowed:
            raise RuntimeError(f"Final URL outside allowlist: {response.url}")
        return response

    raise RuntimeError(f"Too many redirects for {start_url}")


def scrape_source(client: httpx.Client, source: Source, allowed: set[str]) -> dict:
    response = fetch_allowed(client, source.url, allowed)
    extracted = extract_page(response.text)
    text = extracted["text"]
    if len(text) < 200:
        raise ValueError(f"Parsed text too short for {source.url}: {len(text)} chars")

    final_url = str(response.url)
    return {
        "page_id": source.page_id,
        "source_url": source.url,
        "final_url": final_url,
        "redirected": normalize_url(final_url) != normalize_url(source.url),
        "category": source.category,
        "scheme": source.scheme,
        "fetch_timestamp": utc_now(),
        "http_status": response.status_code,
        "content_hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "title": extracted["title"],
        "text": text,
        "structure": extracted["structure"],
        "scrape_status": "ok",
    }


def run_loader(cfg: AppConfig, registry: SourceRegistry) -> list[dict]:
    sources = registry.ingestible()
    allowed = {normalize_url(url) for url in registry.answer_citation_urls()}

    if len(sources) != 5:
        raise RuntimeError(
            f"Expected exactly 5 ingestible sources in registry, found {len(sources)}"
        )

    manifest_entries: list[dict] = []
    successful: list[dict] = []

    with httpx.Client(
        timeout=20.0,
        follow_redirects=False,
        headers={
            "User-Agent": "GrowwMFFAQDemo/1.0 (+official-pages-only)",
            "Accept": "text/html,application/xhtml+xml",
        },
        event_hooks={"request": [make_allowlist_hook(allowed)]},
    ) as client:
        for source in sources:
            try:
                record = scrape_source(client, source, allowed)
                atomic_write_json(
                    cfg.paths.raw_pages_dir / f"{source.page_id}.json",
                    record,
                )
                successful.append(record)
                status = "ok"
                error = None
                print(f"[OK]   {source.page_id} ({len(record['text'])} chars)")
            except Exception as exc:
                status = "failed"
                error = str(exc)
                print(f"[FAIL] {source.page_id}: {error}")

            manifest_entries.append(
                {
                    "page_id": source.page_id,
                    "source_url": source.url,
                    "category": source.category,
                    "scheme": source.scheme,
                    "fetch_timestamp": utc_now(),
                    "http_status": (
                        next(
                            (
                                r["http_status"]
                                for r in successful
                                if r["page_id"] == source.page_id
                            ),
                            None,
                        )
                    ),
                    "content_hash": (
                        next(
                            (
                                r["content_hash"]
                                for r in successful
                                if r["page_id"] == source.page_id
                            ),
                            None,
                        )
                    ),
                    "status": status,
                    "error": error,
                }
            )

    atomic_write_json(
        cfg.paths.page_manifest,
        {
            "generated_at": utc_now(),
            "expected_count": len(sources),
            "success_count": len(successful),
            "pages": manifest_entries,
        },
    )

    if not successful:
        raise RuntimeError("No pages were scraped successfully")

    return successful
