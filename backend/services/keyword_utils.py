"""Utilities for domain-independent keyword extraction."""

from __future__ import annotations

import logging
import re
import string
from collections import Counter
from typing import Iterable

try:
    import nltk
    from nltk.util import ngrams as nltk_ngrams
except Exception:  # pragma: no cover
    nltk = None
    nltk_ngrams = None

logger = logging.getLogger(__name__)

# Common English stopwords + generic job-posting filler words.
DOMAIN_AGNOSTIC_STOPWORDS: set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "can",
    "do", "does", "for", "from", "had", "has", "have", "if", "in", "into", "is", "it",
    "its", "of", "on", "or", "our", "should", "that", "the", "their", "them", "they",
    "this", "those", "to", "was", "were", "will", "with", "you", "your", "we", "us",
    "ability", "able", "active", "additional", "align", "aligned", "alignment",
    "activities", "activity", "adapt", "adaptable", "all", "also", "any", "applicable",
    "appropriate", "assist", "assisting", "assistance", "associated", "availability", "available",
    "basic", "broad", "building", "candidate", "candidates", "capability", "capable",
    "collaborate", "collaboration", "collaborative", "common", "communication", "communications",
    "company", "complete", "comprehensive", "consistent", "contribute", "contribution",
    "create", "creating", "current", "daily", "dedicated", "demonstrate", "demonstrated",
    "desired", "detail", "details", "driven", "dynamic", "effective", "effectively",
    "ensure", "ensuring", "etc", "excellent", "familiarity", "focused", "following",
    "general", "good", "great", "highly", "important", "include", "including", "interpersonal",
    "knowledge", "expert", "experts", "expertise", "experience", "experienced", "proficient", "proficiency",
    "level", "manage", "managing", "multiple", "must", "necessary", "objective",
    "need", "needs", "seeking", "seek", "looking", "look", "require", "required", "requires",
    "wanted", "want", "wants",
    "overall", "organization", "organizational", "position", "preferred", "provide", "providing",
    "required", "requirement", "requirements", "responsibilities", "responsibility", "role",
    "strong", "support", "supporting", "team", "teams", "work", "working",
}

_PUNCT_TRANSLATION_TABLE = str.maketrans({char: " " for char in string.punctuation})
_EXTRA_PUNCT_RE = re.compile(r"[“”‘’–—•·]")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TOKEN_RE_CASED = re.compile(r"[A-Za-z0-9]+")
_PHRASE_SPLIT_RE = re.compile(r"[,;:.!?\n\r()\[\]{}]+")
_NLTK_POS_READY: bool | None = None
_NLTK_POS_WARNING_EMITTED = False
_POS_NOUN_TAGS = {"NN", "NNP"}
_POS_PHRASE_TOKEN_TAGS = {"NN", "NNS", "NNP", "NNPS", "JJ", "JJR", "JJS", "VBG"}
_POS_PHRASE_END_TAGS = {"NN", "NNS", "NNP", "NNPS", "VBG"}
_LOW_SIGNAL_PHRASE_TOKENS = {
    "ability",
    "abilities",
    "experience",
    "knowledge",
    "requirement",
    "requirements",
    "responsibility",
    "responsibilities",
    "skill",
    "skills",
}


def _strip_punctuation(text: str) -> str:
    no_punct = (text or "").translate(_PUNCT_TRANSLATION_TABLE)
    return _EXTRA_PUNCT_RE.sub(" ", no_punct)


def _ensure_nltk_pos_tagger() -> bool:
    """Ensure the NLTK POS tagger is available."""
    global _NLTK_POS_READY

    if _NLTK_POS_READY is not None:
        return _NLTK_POS_READY

    if nltk is None:
        _NLTK_POS_READY = False
        return False

    resource_candidates = (
        "taggers/averaged_perceptron_tagger_eng",
        "taggers/averaged_perceptron_tagger",
    )

    for resource in resource_candidates:
        try:
            nltk.data.find(resource)
            _NLTK_POS_READY = True
            return True
        except LookupError:
            continue

    for download_name in ("averaged_perceptron_tagger_eng", "averaged_perceptron_tagger"):
        try:
            nltk.download(download_name, quiet=True)
        except Exception:
            continue

    for resource in resource_candidates:
        try:
            nltk.data.find(resource)
            _NLTK_POS_READY = True
            return True
        except LookupError:
            continue

    _NLTK_POS_READY = False
    return False


def _tag_tokens(tokens: list[str]) -> list[tuple[str, str]] | None:
    """POS-tag tokens and return None when tagger is unavailable."""
    global _NLTK_POS_WARNING_EMITTED

    if not tokens:
        return []

    if not _ensure_nltk_pos_tagger():
        if not _NLTK_POS_WARNING_EMITTED:
            logger.warning("NLTK POS tagger unavailable; using non-POS fallback keyword filtering")
            _NLTK_POS_WARNING_EMITTED = True
        return None

    try:
        return nltk.pos_tag(tokens)
    except Exception:
        if not _NLTK_POS_WARNING_EMITTED:
            logger.warning("NLTK POS tagging failed; using non-POS fallback keyword filtering")
            _NLTK_POS_WARNING_EMITTED = True
        return None


def _iter_ngrams(tokens: list[str], n: int) -> Iterable[tuple[str, ...]]:
    """Yield n-grams using NLTK when available, otherwise a local fallback."""
    if n <= 0 or len(tokens) < n:
        return

    if nltk_ngrams is not None:
        try:
            yield from nltk_ngrams(tokens, n)
            return
        except Exception:
            pass

    for idx in range(len(tokens) - n + 1):
        yield tuple(tokens[idx : idx + n])


def _filter_pos_nouns(tokens: list[str]) -> list[str]:
    """Keep only nouns/proper nouns (NN, NNP) from token list."""
    tagged = _tag_tokens(tokens)
    if tagged is None:
        return tokens

    return [token for token, tag in tagged if tag in _POS_NOUN_TAGS]


def tokenize_text(text: str) -> list[str]:
    """Tokenize text after lowercasing and punctuation removal."""
    lowered = _strip_punctuation(text).lower()
    no_punct = lowered
    return _TOKEN_RE.findall(no_punct)


def extract_meaningful_terms(
    text: str,
    min_len: int = 3,
    extra_stopwords: Iterable[str] | None = None,
) -> list[str]:
    """Return normalized noun/proper-noun tokens after stopword filtering."""
    blocked = set(DOMAIN_AGNOSTIC_STOPWORDS)
    if extra_stopwords:
        blocked.update(str(word).strip().lower() for word in extra_stopwords if str(word).strip())

    cased_tokens = _TOKEN_RE_CASED.findall(_strip_punctuation(text))
    noun_like_tokens = _filter_pos_nouns(cased_tokens)
    normalized_tokens = [token.lower() for token in noun_like_tokens]

    return [
        token
        for token in normalized_tokens
        if len(token) >= min_len and not token.isdigit() and token not in blocked
    ]


def extract_skill_phrases(
    text: str,
    min_terms: int = 2,
    max_terms: int = 3,
    min_token_len: int = 2,
    extra_stopwords: Iterable[str] | None = None,
) -> list[str]:
    """Extract multi-word skill phrases (bigrams/trigrams) with POS-aware filtering."""
    blocked = set(DOMAIN_AGNOSTIC_STOPWORDS)
    if extra_stopwords:
        blocked.update(str(word).strip().lower() for word in extra_stopwords if str(word).strip())

    phrases: list[str] = []
    lower_bound = max(2, min_terms)
    upper_bound = max(lower_bound, max_terms)
    chunks = [chunk.strip() for chunk in _PHRASE_SPLIT_RE.split(text or "") if chunk.strip()]
    for chunk in chunks:
        cased_tokens = _TOKEN_RE_CASED.findall(_strip_punctuation(chunk))
        token_pairs = [
            (token, token.lower())
            for token in cased_tokens
            if len(token) >= min_token_len and not token.isdigit()
        ]

        if len(token_pairs) < lower_bound:
            continue

        filtered_cased_tokens = [token for token, _ in token_pairs]
        normalized_tokens = [token for _, token in token_pairs]
        tagged = _tag_tokens(filtered_cased_tokens)

        for n in range(lower_bound, upper_bound + 1):
            for idx, gram in enumerate(_iter_ngrams(normalized_tokens, n)):
                gram_tokens = list(gram)

                if any(token in blocked for token in gram_tokens):
                    continue

                if gram_tokens[-1] in _LOW_SIGNAL_PHRASE_TOKENS:
                    continue

                if len(set(gram_tokens)) == 1:
                    continue

                if tagged is not None:
                    gram_tags = [tag for _token, tag in tagged[idx : idx + n]]
                    if len(gram_tags) != n:
                        continue
                    if any(tag not in _POS_PHRASE_TOKEN_TAGS for tag in gram_tags):
                        continue
                    if gram_tags[0] == "VBG":
                        continue
                    if gram_tags[-1] not in _POS_PHRASE_END_TAGS:
                        continue

                phrases.append(" ".join(gram_tokens))

    return phrases


def build_ngram_counter(
    tokens: list[str],
    n_values: tuple[int, ...] = (2, 3),
    extra_stopwords: Iterable[str] | None = None,
) -> Counter[str]:
    """Build n-gram frequencies while skipping n-grams containing stopwords."""
    blocked = set(DOMAIN_AGNOSTIC_STOPWORDS)
    if extra_stopwords:
        blocked.update(str(word).strip().lower() for word in extra_stopwords if str(word).strip())

    ngram_counter: Counter[str] = Counter()
    for n in n_values:
        for gram in _iter_ngrams(tokens, n):
            gram_tokens = [str(token).strip().lower() for token in gram]
            if len(gram_tokens) != n or any(not token for token in gram_tokens):
                continue
            if any(term in blocked for term in gram_tokens):
                continue
            ngram_counter[" ".join(gram_tokens)] += 1
    return ngram_counter
