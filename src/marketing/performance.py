"""서브레딧별 성과 추적 + 전략 조정."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..state import StateDB


@dataclass
class SubredditPerformance:
    subreddit: str
    total_posts: int
    total_comments: int
    avg_score: float
    avg_comments: float
    positive_ratio: float
    effort_score: float    # 우리가 투입한 노력
    roi_score: float       # 성과/노력
    trend: str             # "improving", "stable", "declining"


def get_subreddit_rankings(db: StateDB) -> list[SubredditPerformance]:
    """서브레딧별 성과 순위."""
    # submissions에서 서브레딧별 통계
    subs = db.conn.execute(
        "SELECT subreddit, COUNT(*) as cnt FROM submissions "
        "WHERE subreddit IS NOT NULL GROUP BY subreddit"
    ).fetchall()

    results = []
    for row in subs:
        sub = row["subreddit"]

        # 메트릭 평균
        metrics = db.conn.execute(
            "SELECT AVG(m.upvotes) as avg_up, AVG(m.comment_count) as avg_cm "
            "FROM metrics m JOIN submissions s ON m.submission_id = s.reddit_id "
            "WHERE s.subreddit = ?",
            (sub,),
        ).fetchone()

        avg_score = metrics["avg_up"] or 0 if metrics else 0
        avg_comments = metrics["avg_cm"] or 0 if metrics else 0

        # 우리가 쓴 댓글 수 (노력 지표)
        effort = db.conn.execute(
            "SELECT COUNT(*) as cnt FROM comments WHERE subreddit = ?",
            (sub,),
        ).fetchone()["cnt"]

        # ROI (성과/노력)
        roi = (avg_score + avg_comments * 2) / max(1, effort)

        results.append(SubredditPerformance(
            subreddit=sub,
            total_posts=row["cnt"],
            total_comments=effort,
            avg_score=round(avg_score, 1),
            avg_comments=round(avg_comments, 1),
            positive_ratio=0,  # TODO: 감정 분석 데이터 연동
            effort_score=effort,
            roi_score=round(roi, 2),
            trend="stable",
        ))

    results.sort(key=lambda x: x.roi_score, reverse=True)
    return results


def suggest_effort_reallocation(rankings: list[SubredditPerformance]) -> dict[str, str]:
    """노력 재배분 제안."""
    suggestions = {}
    for r in rankings:
        if r.roi_score >= 5:
            suggestions[r.subreddit] = "increase"  # 노력 증가
        elif r.roi_score >= 2:
            suggestions[r.subreddit] = "maintain"   # 유지
        elif r.roi_score >= 0.5:
            suggestions[r.subreddit] = "reduce"     # 축소
        else:
            suggestions[r.subreddit] = "stop"       # 중단 검토
    return suggestions
