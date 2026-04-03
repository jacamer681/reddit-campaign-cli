"""씨뿌리기 타겟 포스트 선별."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..state import StateDB


@dataclass
class TargetScore:
    url: str
    title: str
    score: int
    num_comments: int
    age_hours: float
    relevance: float     # 0-1
    final_score: float   # 종합 점수
    skip_reason: str | None = None


# 타겟 선정 기준
MAX_AGE_HOURS = 48         # 48시간 이내 포스트만
MIN_SCORE = 1              # 최소 업보트
MIN_COMMENTS = 0           # 최소 댓글
MAX_COMMENTS = 50          # 너무 많으면 묻힘
SKIP_AUTHORS = {"[deleted]", "AutoModerator"}


def score_target(
    title: str,
    score: int,
    num_comments: int,
    created_utc: float,
    author: str,
    topic_keywords: list[str],
) -> TargetScore:
    """포스트의 씨뿌리기 적합도 점수 계산."""
    now = datetime.now(timezone.utc).timestamp()
    age_hours = (now - created_utc) / 3600

    skip_reason = None

    # 필터링
    if age_hours > MAX_AGE_HOURS:
        skip_reason = f"너무 오래됨 ({age_hours:.0f}h)"
    elif score < MIN_SCORE:
        skip_reason = f"업보트 부족 ({score})"
    elif num_comments > MAX_COMMENTS:
        skip_reason = f"댓글 너무 많음 ({num_comments}) — 묻힐 가능성"
    elif author in SKIP_AUTHORS:
        skip_reason = f"작성자 제외 ({author})"

    # 관련성 점수 (0-1)
    title_lower = title.lower()
    if topic_keywords:
        matches = sum(1 for kw in topic_keywords if kw.lower() in title_lower)
        relevance = min(1.0, matches / max(1, len(topic_keywords) * 0.3))
    else:
        relevance = 0.5

    # 신선도 점수 (최신일수록 높음)
    freshness = max(0, 1.0 - age_hours / MAX_AGE_HOURS)

    # 참여도 점수 (적당한 댓글 수가 최적)
    if num_comments <= 5:
        engagement = 0.8  # 초기 — 눈에 잘 띔
    elif num_comments <= 20:
        engagement = 1.0  # 활발 — 좋음
    elif num_comments <= MAX_COMMENTS:
        engagement = 0.5  # 많음 — 묻힐 수 있음
    else:
        engagement = 0.2

    # 업보트 점수
    if score >= 50:
        upvote_score = 1.0
    elif score >= 10:
        upvote_score = 0.8
    elif score >= 3:
        upvote_score = 0.6
    else:
        upvote_score = 0.3

    # 종합 점수
    final = (
        relevance * 0.35
        + freshness * 0.25
        + engagement * 0.25
        + upvote_score * 0.15
    )

    return TargetScore(
        url="",
        title=title,
        score=score,
        num_comments=num_comments,
        age_hours=age_hours,
        relevance=relevance,
        final_score=round(final, 3),
        skip_reason=skip_reason,
    )


def filter_already_commented(targets: list[TargetScore], db: StateDB) -> list[TargetScore]:
    """이미 댓글 단 포스트 제외."""
    commented_urls = set()
    rows = db.conn.execute(
        "SELECT DISTINCT subreddit || ':' || body_hash FROM activity_log "
        "WHERE action_type IN ('comment', 'seeding')"
    ).fetchall()
    for r in rows:
        commented_urls.add(r[0])

    return [t for t in targets if t.url not in commented_urls]


def rank_targets(targets: list[TargetScore], limit: int = 3) -> list[TargetScore]:
    """스킵되지 않은 타겟을 점수순 정렬."""
    valid = [t for t in targets if t.skip_reason is None]
    valid.sort(key=lambda x: x.final_score, reverse=True)
    return valid[:limit]
