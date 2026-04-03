"""부정 댓글 대응 전략."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    TRIVIAL = "trivial"           # "별로" — 무시
    CONSTRUCTIVE = "constructive"  # "X가 더 나은데" — 인정 + 로드맵
    HOSTILE = "hostile"            # "쓰레기" — 1회 팩트 정정
    ATTACK = "attack"             # 인신공격 — 무시
    VIRAL_NEGATIVE = "viral"       # 고upvote 비판 — 신중 대응


class ResponseAction(Enum):
    IGNORE = "ignore"
    RESPOND_ONCE = "respond_once"
    ACKNOWLEDGE = "acknowledge"
    ESCALATE = "escalate"         # 수동 검토 필요


@dataclass
class NegativeAnalysis:
    severity: Severity
    action: ResponseAction
    reason: str
    suggested_response: str | None = None


# 키워드 기반 분류
HOSTILE_KEYWORDS = [
    "garbage", "trash", "crap", "sucks", "terrible", "awful",
    "waste", "scam", "bloat", "bloated", "useless",
]

ATTACK_KEYWORDS = [
    "idiot", "stupid", "dumb", "moron", "shill", "spam",
    "bot", "fake", "liar",
]

CONSTRUCTIVE_PATTERNS = [
    "but", "however", "instead", "rather", "prefer",
    "better", "alternative", "compared to", "why not",
    "have you considered", "what about",
]

# 대응 템플릿
TEMPLATES = {
    Severity.CONSTRUCTIVE: [
        "that's a fair point. {topic} is something I've been thinking about — it's on the list but haven't gotten to it yet",
        "yeah I get that. {topic} is definitely a tradeoff. the way I see it is {reasoning}",
        "totally valid feedback. I'll look into {topic} — appreciate the honest take",
    ],
    Severity.HOSTILE: [
        "fair enough, it's not for everyone. happy to hear specific feedback if you have any",
        "I hear you. {topic} is a conscious tradeoff — {reasoning}. but I get it's not ideal for everyone",
    ],
}


def analyze_negative(
    body: str,
    score: int = 0,
    upvotes: int = 0,
) -> NegativeAnalysis:
    """부정 댓글 분석 + 대응 전략 결정."""
    body_lower = body.lower()

    # 인신공격 감지
    attack_count = sum(1 for kw in ATTACK_KEYWORDS if kw in body_lower)
    if attack_count >= 1:
        return NegativeAnalysis(
            severity=Severity.ATTACK,
            action=ResponseAction.IGNORE,
            reason=f"인신공격 감지 ({attack_count}개 키워드)",
        )

    # 바이럴 네거티브 (고upvote 비판)
    hostile_count = sum(1 for kw in HOSTILE_KEYWORDS if kw in body_lower)
    if hostile_count >= 1 and upvotes >= 20:
        return NegativeAnalysis(
            severity=Severity.VIRAL_NEGATIVE,
            action=ResponseAction.ESCALATE,
            reason=f"고upvote({upvotes}) 비판 — 신중 대응 필요",
        )

    # 적대적
    if hostile_count >= 2:
        return NegativeAnalysis(
            severity=Severity.HOSTILE,
            action=ResponseAction.RESPOND_ONCE,
            reason=f"적대적 표현 {hostile_count}개",
            suggested_response=TEMPLATES[Severity.HOSTILE][0],
        )

    # 건설적 비판
    constructive_count = sum(1 for p in CONSTRUCTIVE_PATTERNS if p in body_lower)
    if constructive_count >= 1 or (hostile_count <= 1 and len(body) > 50):
        return NegativeAnalysis(
            severity=Severity.CONSTRUCTIVE,
            action=ResponseAction.ACKNOWLEDGE,
            reason="건설적 비판 — 인정 + 답변",
            suggested_response=TEMPLATES[Severity.CONSTRUCTIVE][0],
        )

    # 사소한 부정
    return NegativeAnalysis(
        severity=Severity.TRIVIAL,
        action=ResponseAction.IGNORE,
        reason="사소한 부정 — 무시",
    )


def should_respond(analysis: NegativeAnalysis) -> bool:
    """응답해야 하는지."""
    return analysis.action in (ResponseAction.RESPOND_ONCE, ResponseAction.ACKNOWLEDGE)


def get_escalation_status(negative_ratio: float, total_comments: int) -> str:
    """포스트 전체 부정 비율 체크."""
    if total_comments < 5:
        return "insufficient_data"
    if negative_ratio > 0.4:
        return "critical"  # 40% 이상 부정 — 수동 검토
    if negative_ratio > 0.2:
        return "warning"   # 20% 이상 — 주의
    return "normal"
