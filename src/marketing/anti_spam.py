"""스팸 방지 + 자연스러운 행동 시뮬레이션."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..state import StateDB


@dataclass
class DailyBudget:
    posts_used: int
    posts_limit: int
    comments_used: int
    comments_limit: int
    can_post: bool
    can_comment: bool
    next_reset: str  # 내일 0시


@dataclass
class SpamCheckResult:
    allowed: bool
    reason: str
    suggested_delay: float = 0  # 초


# 기본 제한
MAX_POSTS_PER_DAY = 2
MAX_COMMENTS_PER_DAY = 8
MAX_COMMENTS_PER_SUB_PER_DAY = 3
MIN_COMMENT_INTERVAL_SEC = 120   # 최소 2분
MAX_COMMENT_INTERVAL_SEC = 600   # 최대 10분
MIN_POST_INTERVAL_SEC = 14400    # 포스트 간 최소 4시간


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def get_daily_budget(db: StateDB) -> DailyBudget:
    """오늘의 남은 활동 예산."""
    today = _today_str()
    rows = db.conn.execute(
        "SELECT action_type, COUNT(*) as cnt FROM activity_log "
        "WHERE date(created_at) = ? GROUP BY action_type",
        (today,),
    ).fetchall()

    counts = {r["action_type"]: r["cnt"] for r in rows}
    posts = counts.get("post", 0)
    comments = counts.get("comment", 0) + counts.get("seeding", 0)

    return DailyBudget(
        posts_used=posts,
        posts_limit=MAX_POSTS_PER_DAY,
        comments_used=comments,
        comments_limit=MAX_COMMENTS_PER_DAY,
        can_post=posts < MAX_POSTS_PER_DAY,
        can_comment=comments < MAX_COMMENTS_PER_DAY,
        next_reset=f"{today} → tomorrow 00:00",
    )


def check_spam(db: StateDB, action_type: str, subreddit: str, body: str = "") -> SpamCheckResult:
    """액션 전 스팸 체크."""
    today = _today_str()

    # 1. 일일 한도
    budget = get_daily_budget(db)
    if action_type == "post" and not budget.can_post:
        return SpamCheckResult(
            allowed=False,
            reason=f"일일 포스트 한도 초과 ({budget.posts_used}/{budget.posts_limit})",
        )
    if action_type in ("comment", "seeding") and not budget.can_comment:
        return SpamCheckResult(
            allowed=False,
            reason=f"일일 댓글 한도 초과 ({budget.comments_used}/{budget.comments_limit})",
        )

    # 2. 서브레딧별 댓글 한도
    if action_type in ("comment", "seeding"):
        sub_count = db.conn.execute(
            "SELECT COUNT(*) as cnt FROM activity_log "
            "WHERE date(created_at) = ? AND subreddit = ? AND action_type IN ('comment', 'seeding')",
            (today, subreddit),
        ).fetchone()["cnt"]
        if sub_count >= MAX_COMMENTS_PER_SUB_PER_DAY:
            return SpamCheckResult(
                allowed=False,
                reason=f"r/{subreddit} 일일 댓글 한도 ({sub_count}/{MAX_COMMENTS_PER_SUB_PER_DAY})",
            )

    # 3. 시간 간격 체크
    last_action = db.conn.execute(
        "SELECT created_at FROM activity_log "
        "WHERE action_type = ? ORDER BY created_at DESC LIMIT 1",
        (action_type,),
    ).fetchone()

    if last_action:
        last_time = datetime.fromisoformat(last_action["created_at"])
        elapsed = (datetime.now() - last_time).total_seconds()

        if action_type == "post" and elapsed < MIN_POST_INTERVAL_SEC:
            wait = MIN_POST_INTERVAL_SEC - elapsed
            return SpamCheckResult(
                allowed=False,
                reason=f"포스트 쿨다운 ({int(wait)}초 남음, 최소 4시간)",
                suggested_delay=wait,
            )
        if action_type in ("comment", "seeding") and elapsed < MIN_COMMENT_INTERVAL_SEC:
            wait = MIN_COMMENT_INTERVAL_SEC - elapsed
            return SpamCheckResult(
                allowed=False,
                reason=f"댓글 쿨다운 ({int(wait)}초 남음, 최소 2분)",
                suggested_delay=wait,
            )

    # 4. 중복 체크
    if body:
        body_hash = hashlib.sha256(body.strip().lower().encode()).hexdigest()[:16]
        dup = db.conn.execute(
            "SELECT id FROM activity_log WHERE body_hash = ?", (body_hash,)
        ).fetchone()
        if dup:
            return SpamCheckResult(
                allowed=False,
                reason="중복 콘텐츠 (이미 동일 내용 게시됨)",
            )

    return SpamCheckResult(allowed=True, reason="OK")


def log_activity(db: StateDB, action_type: str, subreddit: str, body: str = ""):
    """활동 기록."""
    body_hash = hashlib.sha256(body.strip().lower().encode()).hexdigest()[:16] if body else ""
    db.conn.execute(
        "INSERT INTO activity_log (action_type, subreddit, body_hash, created_at) VALUES (?, ?, ?, ?)",
        (action_type, subreddit, body_hash, datetime.now().isoformat()),
    )
    db.conn.commit()


def get_human_delay() -> float:
    """자연스러운 랜덤 딜레이 (초)."""
    # 대부분 2-5분, 가끔 7-10분
    if random.random() < 0.7:
        return random.uniform(120, 300)
    return random.uniform(300, 600)


def get_typing_delay(text_length: int) -> float:
    """타이핑 시뮬레이션 딜레이."""
    # 평균 타이핑 속도: 40-80 WPM → 문자당 0.15-0.3초
    chars_per_sec = random.uniform(3, 7)
    return text_length / chars_per_sec
