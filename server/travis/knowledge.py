"""Tiny knowledge-base search over markdown files (no vector DB needed to start).

Each file is split on '## ' headings. Sections whose heading contains
'[CONFIDENTIAL]' or '[INTERNAL]' are never returned to callers.
Swap this for your platform's knowledge base or a vector store when you
outgrow it; the tool contract (search_knowledge -> short passages) stays the same.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

from .settings import get_settings

STOP = set("the a an and or of to in for on is are was be with what how do does your you our we i it at by from this that can".split())


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9']+", text.lower()) if t not in STOP and len(t) > 1]


@lru_cache(maxsize=2)
def _index(directory: str) -> list[dict]:
    chunks = []
    for path in sorted(Path(directory).glob("*.md")):
        text = path.read_text()
        parts = re.split(r"\n(?=## )", text)
        for part in parts:
            heading = part.strip().splitlines()[0].lstrip("# ").strip() if part.strip() else path.stem
            private = "[CONFIDENTIAL]" in heading or "[INTERNAL]" in heading
            chunks.append({"file": path.name, "heading": heading, "text": part.strip(),
                           "tokens": _tokens(part), "private": private})
    return chunks


def search(query: str, limit: int = 3, include_private: bool = False) -> list[dict]:
    chunks = [c for c in _index(get_settings().knowledge_dir) if include_private or not c["private"]]
    q = _tokens(query)
    if not q or not chunks:
        return []
    n = len(chunks)
    df = {t: sum(1 for c in chunks if t in c["tokens"]) for t in set(q)}
    scored = []
    for c in chunks:
        score = 0.0
        for t in q:
            tf = c["tokens"].count(t)
            if tf:
                idf = math.log(1 + n / (1 + df[t]))
                score += idf * (tf / (tf + 1.2)) * (2.0 if t in c["heading"].lower() else 1.0)
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [{"source": f"{c['file']} › {c['heading']}", "text": c["text"][:900]} for _, c in scored[:limit]]


def reset_index() -> None:
    _index.cache_clear()
