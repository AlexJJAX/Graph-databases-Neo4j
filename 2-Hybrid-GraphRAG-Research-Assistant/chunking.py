"""Corpus validation and deterministic word-overlap chunking."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_MAX_WORDS = 140
DEFAULT_OVERLAP_WORDS = 25


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    chunk_id: str
    paper_id: str
    section: str
    sequence: int
    text: str
    embedding_text: str
    content_hash: str


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def chunk_words(
    text: str,
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[str]:
    """Split text into bounded word chunks with deterministic overlap."""
    if max_words < 20:
        raise ValueError("max_words must be at least 20")
    if overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("overlap_words must be between 0 and max_words - 1")

    words = normalize_text(text).split()
    if not words:
        return []

    step = max_words - overlap_words
    chunks: list[str] = []
    for start in range(0, len(words), step):
        piece = words[start : start + max_words]
        if not piece:
            break
        chunks.append(" ".join(piece))
        if start + max_words >= len(words):
            break
    return chunks


def _required_string(item: Mapping[str, Any], field: str, paper_id: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Paper '{paper_id}' requires a non-empty '{field}'")
    return value.strip()


def _string_list(item: Mapping[str, Any], field: str, paper_id: str) -> list[str]:
    value = item.get(field, [])
    if not isinstance(value, list) or not all(
        isinstance(entry, str) and entry.strip() for entry in value
    ):
        raise ValueError(f"Paper '{paper_id}' field '{field}' must be a string list")
    return [entry.strip() for entry in value]


def load_corpus(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Corpus must be a non-empty JSON array")

    paper_ids: set[str] = set()
    papers: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Every corpus entry must be an object")
        paper_id = _required_string(item, "paperId", "unknown")
        if paper_id in paper_ids:
            raise ValueError(f"Duplicate paperId: {paper_id}")
        paper_ids.add(paper_id)

        sections = item.get("sections")
        if not isinstance(sections, list) or not sections:
            raise ValueError(f"Paper '{paper_id}' requires at least one section")
        normalized_sections = []
        for section in sections:
            if not isinstance(section, dict):
                raise ValueError(f"Paper '{paper_id}' has an invalid section")
            normalized_sections.append(
                {
                    "heading": _required_string(section, "heading", paper_id),
                    "text": _required_string(section, "text", paper_id),
                }
            )

        year = item.get("year")
        if not isinstance(year, int) or not 1900 <= year <= 2100:
            raise ValueError(f"Paper '{paper_id}' has an invalid year")

        papers.append(
            {
                "paperId": paper_id,
                "title": _required_string(item, "title", paper_id),
                "year": year,
                "abstract": _required_string(item, "abstract", paper_id),
                "sourceUrl": _required_string(item, "sourceUrl", paper_id),
                "authors": _string_list(item, "authors", paper_id),
                "topics": _string_list(item, "topics", paper_id),
                "methods": _string_list(item, "methods", paper_id),
                "datasets": _string_list(item, "datasets", paper_id),
                "cites": _string_list(item, "cites", paper_id),
                "sections": normalized_sections,
            }
        )

    unknown_citations = {
        cited
        for paper in papers
        for cited in paper["cites"]
        if cited not in paper_ids
    }
    if unknown_citations:
        raise ValueError(
            "Corpus cites unknown paper IDs: " + ", ".join(sorted(unknown_citations))
        )
    return papers


def build_chunks(
    paper: Mapping[str, Any],
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    sequence = 0
    for section_index, section in enumerate(paper["sections"]):
        pieces = chunk_words(
            section["text"],
            max_words=max_words,
            overlap_words=overlap_words,
        )
        for part_index, piece in enumerate(pieces):
            chunk_id = f"{paper['paperId']}:s{section_index:02d}:p{part_index:02d}"
            drafts.append(
                ChunkDraft(
                    chunk_id=chunk_id,
                    paper_id=paper["paperId"],
                    section=section["heading"],
                    sequence=sequence,
                    text=piece,
                    embedding_text=(
                        f"{paper['title']}\n{section['heading']}\n{piece}"
                    ),
                    content_hash=content_hash(piece),
                )
            )
            sequence += 1
    return drafts


def corpus_hash(paper: Mapping[str, Any], chunks: Iterable[ChunkDraft]) -> str:
    fingerprint = {
        "paperId": paper["paperId"],
        "title": paper["title"],
        "year": paper["year"],
        "abstract": paper["abstract"],
        "authors": paper["authors"],
        "topics": paper["topics"],
        "methods": paper["methods"],
        "datasets": paper["datasets"],
        "cites": paper["cites"],
        "chunks": [chunk.content_hash for chunk in chunks],
    }
    return content_hash(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False))
