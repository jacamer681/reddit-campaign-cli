"""콘텐츠 변형 엔진 — 댓글이 템플릿처럼 보이지 않게."""

from __future__ import annotations

import hashlib
import random


# 동의어 치환 맵
SYNONYMS = {
    "really": ["actually", "honestly", "genuinely"],
    "cool": ["neat", "solid", "nice", "interesting"],
    "great": ["solid", "nice", "good", "decent"],
    "I think": ["imo", "from what I've seen", "in my experience"],
    "a lot": ["quite a bit", "a ton", "plenty"],
    "pretty": ["fairly", "reasonably", "quite"],
    "awesome": ["solid", "really good", "impressive"],
    "use": ["run", "try", "work with"],
    "check out": ["look into", "take a look at", "have a look at"],
    "but": ["though", "although", "but then again"],
    "honestly": ["tbh", "real talk", "genuinely"],
    "I've been": ["been", "I started", "I've started"],
}

# 필러 표현 (랜덤 삽입)
FILLERS = [
    "tbh", "honestly", "fwiw", "imo", "ngl",
    "interestingly", "funny enough", "worth noting",
]

# 문장 끝 변형
ENDINGS = {
    ".": [".", ".", ".", ""],  # 75% 마침표, 25% 생략
    "!": ["!", ".", ""],
}


def vary(body: str, level: float = 0.3) -> str:
    """텍스트에 자연스러운 변형 적용.

    level: 0.0 = 변형 없음, 1.0 = 강한 변형
    """
    if level <= 0 or not body:
        return body

    result = body

    # 1. 동의어 치환
    for original, replacements in SYNONYMS.items():
        if original.lower() in result.lower() and random.random() < level:
            replacement = random.choice(replacements)
            # 대소문자 보존
            if original[0].isupper():
                replacement = replacement.capitalize()
            result = result.replace(original, replacement, 1)

    # 2. 대소문자 변형 (첫 글자)
    if random.random() < level * 0.5:
        if result[0].isupper():
            result = result[0].lower() + result[1:]

    # 3. 마침표 변형
    if random.random() < level * 0.3:
        if result.endswith("."):
            result = result[:-1]

    return result


def generate_variants(body: str, count: int = 3) -> list[str]:
    """여러 변형 생성."""
    variants = [body]  # 원본 포함
    for i in range(count - 1):
        level = 0.2 + (i * 0.15)
        v = vary(body, level=min(level, 0.6))
        if v != body and v not in variants:
            variants.append(v)
    return variants


def is_too_similar(body: str, recent_comments: list[str], threshold: float = 0.6) -> bool:
    """기존 댓글과 너무 유사한지 체크 (Jaccard 유사도)."""
    body_words = set(body.lower().split())
    if not body_words:
        return False

    for existing in recent_comments:
        existing_words = set(existing.lower().split())
        if not existing_words:
            continue

        intersection = body_words & existing_words
        union = body_words | existing_words
        similarity = len(intersection) / len(union) if union else 0

        if similarity > threshold:
            return True

    return False


def get_recent_comment_bodies(db, limit: int = 20) -> list[str]:
    """최근 댓글 내용 조회."""
    rows = db.conn.execute(
        "SELECT body FROM comments ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [r["body"] for r in rows if r["body"]]
