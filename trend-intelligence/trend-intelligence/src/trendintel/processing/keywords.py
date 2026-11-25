"""Keyword / key-phrase extraction.

Purpose: turn each article's text into a set of candidate topic terms
(unigrams and bigrams) using transparent, dependency-free rules: tokenise,
drop stop-words, apply light singularisation, and never build a phrase across
punctuation or a stop-word. The goal is explainability over cleverness.
"""
from __future__ import annotations

import re

from ..models import Article

_STOPWORDS_TEXT = """
a about above across after again against all almost also although always am among an and another any anyone
are aren around as at back be because been before being below best better between both but by can cannot
could day days did do does doing done down during each either else enough even ever every few first for
from further get gets getting go goes going got had has have having he her here hers him his how however i if
in into is isn it its itself just last least less let like likely made make makes making many may me might
more most much must my new next no nor not now of off often on once one only onto or other our out over own
per people perhaps put rather really said same say says see seen several she should since so some something
still such take takes than that the their them then there these they thing things this those though three
through thus time to today too top two under until up upon us use used uses using very via vs want was way
we week weeks well were what when where whether which while who whom whose why will with within without
would year years yet you your
announce announces announced announcing launch launches launched launching unveil unveils unveiled release
releases released report reports reported reporting show shows showed hn ask tell tells amid raises raised
gets becomes become became according breaking latest update updates news video watch review reviews guide
tips how-to inc co corp ltd llc
"""
STOPWORDS = frozenset(_STOPWORDS_TEXT.split())
SHORT_ALLOWED = frozenset({"ai", "ml", "vr", "ar", "ev", "5g", "3d", "c++", "c#"})

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#]*(?:['’.\-][A-Za-z0-9+#]+)*")
_POSSESSIVE_RE = re.compile(r"['’]s$", re.IGNORECASE)
DESCRIPTION_CHARS = 300


def normalize_token(token: str) -> str:
    """Lower-case, strip possessives and a trailing plural 's' (``chips`` -> ``chip``)."""
    t = _POSSESSIVE_RE.sub("", token).lower().strip(".'’")
    if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is", "os")):
        t = t[:-1]
    return t


def _is_content_token(norm: str, raw_lower: str) -> bool:
    if len(norm) < 2 or norm in STOPWORDS or raw_lower in STOPWORDS:
        return False
    if norm.replace(".", "").replace("-", "").isdigit():
        return False
    return True


def extract_terms(text: str) -> dict[str, str]:
    """Return ``{normalised term: display surface form}`` for unigrams and bigrams in ``text``."""
    # Each entry is (norm, surface) or None where a stop-word/punctuation breaks a phrase.
    sequence: list[tuple[str, str] | None] = []
    previous_end = 0
    for match in TOKEN_RE.finditer(text):
        if text[previous_end : match.start()].strip():  # punctuation between tokens
            sequence.append(None)
        previous_end = match.end()
        raw = match.group(0)
        surface = _POSSESSIVE_RE.sub("", raw)
        norm = normalize_token(raw)
        sequence.append((norm, surface) if _is_content_token(norm, raw.lower()) else None)

    terms: dict[str, str] = {}
    for i, item in enumerate(sequence):
        if item is None:
            continue
        norm, surface = item
        if len(norm) >= 4 or norm in SHORT_ALLOWED:
            terms.setdefault(norm, surface)
        nxt = sequence[i + 1] if i + 1 < len(sequence) else None
        if nxt is not None:
            terms.setdefault(f"{norm} {nxt[0]}", f"{surface} {nxt[1]}")
    return terms


def extract_article_terms(article: Article) -> dict[str, str]:
    """Terms from the title plus the start of the description."""
    return extract_terms(f"{article.title}. {article.description[:DESCRIPTION_CHARS]}")
