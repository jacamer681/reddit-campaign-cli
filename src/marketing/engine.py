"""마케팅 엔진 — 모든 판단의 중심.

클로드 코드가 이 엔진을 통해 모든 Reddit 액션을 제어.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..state import StateDB
from .account_health import HealthReport, RiskLevel, check_health
from .anti_spam import (
    DailyBudget, SpamCheckResult,
    check_spam, get_daily_budget, get_human_delay, log_activity,
)
from .content_variation import generate_variants, is_too_similar, get_recent_comment_bodies, vary
from .negative_response import NegativeAnalysis, analyze_negative, should_respond
from .subreddit_rules import RuleCheckResult, check_rules, get_profile
from .target_selection import TargetScore, score_target, rank_targets
from .timing import TimingAdvice, TimingGrade, check_timing


class ActionType(Enum):
    POST = "post"
    COMMENT = "comment"
    SEEDING = "seeding"
    REPLY = "reply"
    KARMA_BUILD = "karma_build"  # 카르마 빌딩 (앱 언급 없이)


@dataclass
class Action:
    action_type: ActionType
    subreddit: str
    title: str = ""
    body: str = ""
    target_url: str = ""
    day_id: str = ""
    is_self_promo: bool = False


@dataclass
class PreFlightResult:
    allowed: bool
    action: Action
    timing: TimingAdvice | None = None
    health: HealthReport | None = None
    spam_check: SpamCheckResult | None = None
    rule_check: RuleCheckResult | None = None
    warnings: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    suggested_delay: float = 0
    varied_body: str = ""  # 변형된 본문


# 카르마 빌딩에 좋은 서브레딧 (앱 관련 + 일반)
KARMA_SUBS = [
    "commandline", "programming", "rust", "webdev",
    "vim", "neovim", "linux", "opensource",
    "python", "golang", "devops",
]

# 카르마 빌딩 검색 키워드
KARMA_TOPICS = {
    "commandline": ["terminal workflow", "cli tools", "shell setup"],
    "programming": ["developer tools", "IDE setup", "productivity"],
    "rust": ["tauri", "portable-pty", "wasm"],
    "webdev": ["developer productivity", "web tooling"],
    "vim": ["terminal multiplexer", "neovim config"],
    "neovim": ["terminal setup", "plugin"],
    "linux": ["terminal emulator", "desktop linux"],
    "devops": ["monitoring tools", "deployment"],
}


class MarketingEngine:
    """마케팅 판단 엔진."""

    def __init__(self, db: StateDB):
        self.db = db

    def pre_flight_check(self, action: Action) -> PreFlightResult:
        """액션 실행 전 전체 체크. 클로드 코드가 이 결과를 보고 판단."""
        warnings = []
        blocks = []

        # 1. 계정 건강도
        health = check_health(self.db)
        if not health.can_proceed:
            blocks.append(f"계정 위험: {', '.join(health.warnings)}")
        elif health.warnings:
            warnings.extend(health.warnings)

        # 2. 타이밍
        timing = check_timing(action.subreddit)
        if timing.grade == TimingGrade.AVOID:
            blocks.append(f"타이밍: {timing.reason}")
        elif timing.grade == TimingGrade.POOR:
            warnings.append(f"타이밍: {timing.reason}")

        # 3. 스팸 체크
        spam = check_spam(self.db, action.action_type.value, action.subreddit, action.body)
        if not spam.allowed:
            blocks.append(f"스팸 방지: {spam.reason}")

        # 4. 서브레딧 규칙
        rules = check_rules(action.subreddit, action.action_type.value, action.is_self_promo)
        if not rules.allowed:
            blocks.extend(rules.blocks)
        warnings.extend(rules.warnings)

        # 5. 콘텐츠 변형 + 중복 체크
        varied_body = action.body
        if action.body and action.action_type in (ActionType.SEEDING, ActionType.COMMENT, ActionType.KARMA_BUILD):
            # 기존 댓글과 유사도 체크
            recent = get_recent_comment_bodies(self.db)
            if is_too_similar(action.body, recent):
                warnings.append("기존 댓글과 유사 — 변형 적용")
                varied_body = vary(action.body, level=0.4)

        # 6. 딜레이 계산
        suggested_delay = 0
        if spam.suggested_delay > 0:
            suggested_delay = spam.suggested_delay
        elif action.action_type != ActionType.POST:
            suggested_delay = get_human_delay()

        allowed = len(blocks) == 0
        return PreFlightResult(
            allowed=allowed,
            action=action,
            timing=timing,
            health=health,
            spam_check=spam,
            rule_check=rules,
            warnings=warnings,
            blocks=blocks,
            suggested_delay=suggested_delay,
            varied_body=varied_body,
        )

    def log_executed(self, action: Action):
        """실행 완료 기록."""
        log_activity(self.db, action.action_type.value, action.subreddit, action.body)

    def get_budget(self) -> DailyBudget:
        """오늘 남은 활동 예산."""
        return get_daily_budget(self.db)

    def get_health(self) -> HealthReport:
        """계정 건강도."""
        return check_health(self.db)

    def analyze_comment(self, body: str, score: int = 0, upvotes: int = 0) -> NegativeAnalysis:
        """댓글 감정 분석."""
        return analyze_negative(body, score, upvotes)

    def get_karma_building_plan(self, count: int = 3) -> list[Action]:
        """카르마 빌딩 액션 생성.

        앱 언급 없이 서브레딧에서 도움이 되는 댓글을 달 계획.
        """
        budget = self.get_budget()
        available = budget.comments_limit - budget.comments_used
        count = min(count, available)

        if count <= 0:
            return []

        actions = []
        import random
        subs = random.sample(KARMA_SUBS, min(count, len(KARMA_SUBS)))

        for sub in subs[:count]:
            topics = KARMA_TOPICS.get(sub, ["developer tools"])
            topic = random.choice(topics)
            actions.append(Action(
                action_type=ActionType.KARMA_BUILD,
                subreddit=sub,
                body="",  # 브라우저에서 포스트 읽고 직접 작성
                target_url="",
                is_self_promo=False,
            ))

        return actions

    def score_seeding_targets(
        self,
        posts: list[dict],
        topic_keywords: list[str],
    ) -> list[TargetScore]:
        """씨뿌리기 타겟 점수 매기기."""
        targets = []
        for p in posts:
            t = score_target(
                title=p.get("title", ""),
                score=p.get("score", 0),
                num_comments=p.get("num_comments", 0),
                created_utc=p.get("created_utc", 0),
                author=p.get("author", ""),
                topic_keywords=topic_keywords,
            )
            t.url = p.get("url", "")
            targets.append(t)
        return rank_targets(targets)

    def get_content_variants(self, body: str, count: int = 3) -> list[str]:
        """콘텐츠 변형 후보 생성."""
        return generate_variants(body, count)

    def format_status(self) -> str:
        """현재 상태 요약 (클로드 코드가 읽을 수 있는 텍스트)."""
        health = self.get_health()
        budget = self.get_budget()

        lines = [
            "=== Marketing Engine Status ===",
            f"Risk Level: {health.risk_level.value.upper()}",
            f"Posts Today: {budget.posts_used}/{budget.posts_limit}",
            f"Comments Today: {budget.comments_used}/{budget.comments_limit}",
            f"Can Post: {'Yes' if budget.can_post else 'No'}",
            f"Can Comment: {'Yes' if budget.can_comment else 'No'}",
        ]

        if health.cooldown_remaining_sec > 0:
            lines.append(f"Post Cooldown: {health.cooldown_remaining_sec // 60}분 남음")

        if health.warnings:
            lines.append("Warnings:")
            for w in health.warnings:
                lines.append(f"  - {w}")

        return "\n".join(lines)
