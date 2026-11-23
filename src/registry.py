from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


ROLES = {"ingested", "reference", "education"}
ALLOWED_USES = {"answer_citation", "refusal_link", "none"}


@dataclass(frozen=True)
class Source:
    page_id: str
    title: str
    url: str
    category: str
    scheme: str
    role: str
    allowed_use: str


class SourceRegistry:
    def __init__(self, path: Path):
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        self.sources = [Source(**item) for item in data.get("sources", [])]
        self._validate()

    def _validate(self) -> None:
        seen: set[str] = set()
        for source in self.sources:
            if source.role not in ROLES:
                raise ValueError(f"Invalid role '{source.role}' for {source.page_id}")
            if source.allowed_use not in ALLOWED_USES:
                raise ValueError(f"Invalid allowed_use '{source.allowed_use}' for {source.page_id}")
            if source.page_id in seen:
                raise ValueError(f"Duplicate page_id in source registry: {source.page_id}")
            seen.add(source.page_id)

    def ingestible(self) -> list[Source]:
        """Only these URLs may be requested by the scraper."""
        return [
            source
            for source in self.sources
            if source.role == "ingested" and source.allowed_use == "answer_citation"
        ]

    def answer_citation_urls(self) -> set[str]:
        return {source.url for source in self.ingestible()}

    def refusal_links(self) -> list[Source]:
        return [source for source in self.sources if source.allowed_use == "refusal_link"]

    def default_refusal_link(self) -> str:
        links = self.refusal_links()
        if links:
            return links[0].url
        amc = next((s for s in self.ingestible() if s.category == "amc"), None)
        if amc:
            return amc.url
        raise RuntimeError("No refusal link available in source registry")
