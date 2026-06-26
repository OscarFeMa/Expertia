"""
Content Quality Scorer for Expertia

Flesch Reading Ease, Dale-Chall, Type-Token Ratio, clickbait detection,
and TF-IDF cosine similarity — no heavy dependencies.
"""

import re
import math
import logging
from collections import Counter
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Approximate syllable count per word for Flesch
_SYLLABLE_MULTIPLIER = 1.0 / 3.0

_CLICKBAIT_PATTERNS = [
    r'\b\d+\b', r'you won\'?t believe', r'this will', r'what no one tells',
    r'shocked?', r'amazing', r'unbelievable', r'jaw-dropping',
    r'you need to see', r'blows your mind', r'secret', r'guaranteed',
    r'what happens when', r'number \d+', r'top \d+', r'\d+ things',
    r'\d+ ways', r'\d+ reasons', r'will never', r'this is why',
    r'the reason why', r'one weird trick', r'doctors hate',
    r'you won\'?t guess', r'what no one will tell you',
]

_DALE_CHALL_EASY: Optional[set] = None


def _load_dale_chall() -> set:
    global _DALE_CHALL_EASY
    if _DALE_CHALL_EASY is not None:
        return _DALE_CHALL_EASY
    _DALE_CHALL_EASY = {
        'a', 'about', 'after', 'all', 'also', 'an', 'and', 'any', 'are', 'as',
        'at', 'back', 'be', 'because', 'been', 'but', 'by', 'can', 'could',
        'did', 'do', 'down', 'each', 'few', 'find', 'first', 'for', 'from',
        'get', 'go', 'good', 'had', 'has', 'have', 'he', 'her', 'here', 'him',
        'his', 'how', 'if', 'in', 'into', 'is', 'it', 'its', 'just', 'like',
        'long', 'look', 'made', 'make', 'man', 'many', 'may', 'me', 'more',
        'most', 'much', 'must', 'my', 'new', 'no', 'not', 'now', 'of', 'on',
        'one', 'only', 'or', 'other', 'our', 'out', 'over', 'people', 'said',
        'same', 'see', 'she', 'so', 'some', 'such', 'take', 'than', 'that',
        'the', 'their', 'them', 'then', 'there', 'these', 'they', 'thing',
        'this', 'those', 'three', 'through', 'time', 'to', 'two', 'up', 'us',
        'use', 'very', 'was', 'water', 'way', 'we', 'were', 'what', 'when',
        'where', 'which', 'who', 'will', 'with', 'word', 'would', 'years',
        'you', 'your',
    }
    return _DALE_CHALL_EASY


def flesch_reading_ease(text: str) -> float:
    if not text or len(text.strip()) < 20:
        return 0.0
    words = text.split()
    sentences = max(text.count('.') + text.count('!') + text.count('?'), 1)
    syllables = sum(max(1, len(w) // 3) for w in words)
    return max(0.0, min(100.0,
        206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syllables / len(words))
    ))


def dale_chall_score(text: str) -> float:
    if not text or len(text.strip()) < 20:
        return 0.0
    easy_set = _load_dale_chall()
    words = text.lower().split()
    if not words:
        return 0.0
    difficult = sum(1 for w in words if w not in easy_set)
    difficult_pct = difficult / len(words) * 100
    sentences = max(text.count('.') + text.count('!') + text.count('?'), 1)
    raw = 0.1579 * difficult_pct + 0.0496 * (len(words) / sentences)
    if difficult_pct > 5:
        raw += 3.6365
    return round(raw, 2)


def type_token_ratio(text: str) -> float:
    if not text or len(text.strip()) < 10:
        return 0.0
    tokens = text.lower().split()
    if len(tokens) < 2:
        return 0.0
    return len(set(tokens)) / len(tokens)


def clickbait_score(title: str) -> int:
    if not title:
        return 0
    title_lower = title.lower()
    return sum(1 for p in _CLICKBAIT_PATTERNS if re.search(p, title_lower))


def cosine_similarity(text_a: str, text_b: str) -> float:
    if not text_a or not text_b:
        return 0.0
    a_words = text_a.lower().split()
    b_words = text_b.lower().split()
    if not a_words or not b_words:
        return 0.0
    a_counts = Counter(a_words)
    b_counts = Counter(b_words)
    intersection = set(a_counts) & set(b_counts)
    dot_product = sum(a_counts[w] * b_counts[w] for w in intersection)
    norm_a = math.sqrt(sum(c * c for c in a_counts.values()))
    norm_b = math.sqrt(sum(c * c for c in b_counts.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


class ContentQualityScorer:
    def __init__(self):
        self._flesch_weight = 0.20
        self._ttr_weight = 0.20
        self._clickbait_penalty = 0.15
        self._length_weight = 0.15
        self._novelty_weight = 0.30

    def score(self, text: str, title: str = "",
              existing_texts: Optional[List[str]] = None) -> Dict:
        flesch = flesch_reading_ease(text)
        dale = dale_chall_score(text)
        ttr = type_token_ratio(text)
        cb = clickbait_score(title)

        cb_norm = max(0.0, 1.0 - cb * 0.2)

        length = len(text)
        if length < 500:
            length_score = length / 500.0
        elif length < 5000:
            length_score = 1.0
        else:
            length_score = 1.0 - (length - 5000) / 20000.0
        length_score = max(0.1, min(1.0, length_score))

        flesch_norm = max(0.0, min(1.0, flesch / 100.0))
        ttr_norm = max(0.0, min(1.0, ttr * 2.0))

        novelty = 1.0
        if existing_texts:
            similarities = [cosine_similarity(text, et) for et in existing_texts if et]
            if similarities:
                max_sim = max(similarities)
                novelty = max(0.0, 1.0 - max_sim)

        composite = (
            self._flesch_weight * flesch_norm
            + self._ttr_weight * ttr_norm
            + self._clickbait_penalty * cb_norm
            + self._length_weight * length_score
            + self._novelty_weight * novelty
        )
        composite = max(0.0, min(1.0, composite))

        return {
            "flesch": round(flesch, 2),
            "dale_chall": dale,
            "ttr": round(ttr, 4),
            "clickbait": cb,
            "length": length,
            "length_score": round(length_score, 3),
            "novelty": round(novelty, 4),
            "composite": round(composite, 4),
        }
