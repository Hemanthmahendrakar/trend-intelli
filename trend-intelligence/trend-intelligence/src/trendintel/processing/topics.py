"""Topic grouping.

Purpose: raw keyword terms are noisy and overlapping ("openai", "gpt-5",
"openai gpt-5"). This module groups terms that describe the same set of
articles into one *topic* using two explainable rules:

1. Jaccard rule: two terms whose article sets overlap strongly (>= 0.6) merge.
2. Containment rule: a more specific phrase merges into a general term it
   contains when it almost always co-occurs with it (>= 0.8 of the phrase's
   articles) and the general term is not vastly more common (<= 2x).

Groups are formed with union-find; the group's label is the most frequent term
(ties prefer two-word phrases).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Topic:
    slug: str
    label: str
    terms: tuple[str, ...]
    article_indices: tuple[int, ...]


def slugify(term: str) -> str:
    text = term.lower().replace("+", " plus ").replace("#", " sharp ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "topic"


def _is_subphrase(small: str, big: str) -> bool:
    return set(small.split()) < set(big.split())


def build_topics(
    article_terms: Sequence[Mapping[str, str]],
    min_df: int = 2,
    jaccard: float = 0.6,
    containment: float = 0.8,
    containment_ratio: float = 2.0,
    max_terms: int = 500,
) -> list[Topic]:
    postings: dict[str, set[int]] = defaultdict(set)
    surfaces: dict[str, Counter] = defaultdict(Counter)
    for index, terms in enumerate(article_terms):
        for term, surface in terms.items():
            postings[term].add(index)
            surfaces[term][surface] += 1

    candidates = sorted((t for t, p in postings.items() if len(p) >= min_df), key=lambda t: (-len(postings[t]), t))
    candidates = candidates[:max_terms]

    parent = {t: t for t in candidates}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(candidates):
        pa = postings[a]
        for b in candidates[i + 1 :]:
            pb = postings[b]
            shared = len(pa & pb)
            if not shared:
                continue
            if shared / (len(pa) + len(pb) - shared) >= jaccard:
                union(a, b)
                continue
            for general, specific in ((a, b), (b, a)):
                pg, ps = postings[general], postings[specific]
                if (
                    _is_subphrase(general, specific)
                    and shared / len(ps) >= containment
                    and len(pg) <= containment_ratio * len(ps)
                ):
                    union(general, specific)
                    break

    groups: dict[str, list[str]] = defaultdict(list)
    for term in candidates:
        groups[find(term)].append(term)

    topics: list[Topic] = []
    used_slugs: set[str] = set()
    for terms in groups.values():
        canonical = max(terms, key=lambda t: (len(postings[t]), 1 if len(t.split()) == 2 else 0, len(t)))
        indices = sorted(set().union(*(postings[t] for t in terms)))
        slug = slugify(canonical)
        base, n = slug, 2
        while slug in used_slugs:
            slug, n = f"{base}-{n}", n + 1
        used_slugs.add(slug)
        topics.append(
            Topic(
                slug=slug,
                label=surfaces[canonical].most_common(1)[0][0],
                terms=tuple(sorted(terms)),
                article_indices=tuple(indices),
            )
        )
    topics.sort(key=lambda t: (-len(t.article_indices), t.slug))
    return topics
