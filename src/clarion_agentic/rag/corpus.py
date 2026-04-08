from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(slots=True)
class CorpusDocument:
    doc_id: str
    source: str
    title: str
    url: str
    text: str
    updated_at: str
    metadata: dict[str, object] = field(default_factory=dict)


def save_corpus(path: Path, documents: list[CorpusDocument]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(asdict(document), ensure_ascii=True) + "\n")


def load_corpus(path: Path) -> list[CorpusDocument]:
    if not path.exists():
        return []

    documents: list[CorpusDocument] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            documents.append(CorpusDocument(**item))
    return documents


def search_corpus(path: Path, query: str, top_k: int = 5) -> list[CorpusDocument]:
    documents = load_corpus(path)
    if not documents:
        return []

    query_terms = set(TOKEN_PATTERN.findall(query.lower()))
    scored: list[tuple[int, CorpusDocument]] = []

    for document in documents:
        haystack = f"{document.title} {document.text}".lower()
        doc_terms = TOKEN_PATTERN.findall(haystack)
        score = sum(doc_terms.count(term) for term in query_terms)
        if score > 0:
            scored.append((score, document))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [document for _, document in scored[:top_k]]
