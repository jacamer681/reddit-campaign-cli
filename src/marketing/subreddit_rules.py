"""서브레딧별 규칙 관리."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubredditProfile:
    name: str
    min_karma: int = 0
    min_account_age_days: int = 0
    self_promo_ratio: float = 0.1   # 10:1 규칙 (홍보 1 : 기여 10)
    self_promo_allowed: bool = True
    max_posts_per_week: int = 2
    requires_flair: bool = False
    allowed_types: list[str] = field(default_factory=lambda: ["text", "link"])
    banned_keywords: list[str] = field(default_factory=list)
    notes: str = ""


# 캠페인 대상 서브레딧 프로필
PROFILES: dict[str, SubredditProfile] = {
    "commandline": SubredditProfile(
        name="commandline",
        min_karma=10,
        self_promo_ratio=0.1,
        notes="터미널 도구 환영. GUI 앱을 'terminal'로 부르면 반발.",
    ),
    "programming": SubredditProfile(
        name="programming",
        min_karma=50,
        min_account_age_days=7,
        self_promo_ratio=0.1,
        notes="10:1 규칙 엄격. 자기 프로젝트 홍보는 기여 10개 후 1개.",
    ),
    "rust": SubredditProfile(
        name="rust",
        min_karma=20,
        self_promo_ratio=0.2,
        notes="Rust 코드/크레이트 관련만. 일반 앱 홍보 부정적.",
    ),
    "ClaudeAI": SubredditProfile(
        name="ClaudeAI",
        min_karma=5,
        self_promo_ratio=0.3,
        notes="AI 통합 사례 환영. 사용 경험 중심.",
    ),
    "webdev": SubredditProfile(
        name="webdev",
        min_karma=20,
        self_promo_ratio=0.1,
        notes="Show-off Saturday 활용. 평일 셀프 프로모 주의.",
    ),
    "SideProject": SubredditProfile(
        name="SideProject",
        min_karma=5,
        self_promo_allowed=True,
        self_promo_ratio=0.5,
        notes="사이드프로젝트 공유 전용. 셀프프로모 OK.",
    ),
    "macapps": SubredditProfile(
        name="macapps",
        min_karma=10,
        allowed_types=["text", "link"],
        notes="macOS 앱 전용. 가격/무료 명시 필요.",
    ),
    "tauri": SubredditProfile(
        name="tauri",
        min_karma=5,
        self_promo_ratio=0.3,
        notes="Tauri 프레임워크 커뮤니티. 기술 디테일 중요.",
    ),
    "neovim": SubredditProfile(
        name="neovim",
        min_karma=10,
        notes="터미널 순수주의자 많음. Electron/Tauri에 회의적.",
    ),
    "devops": SubredditProfile(
        name="devops",
        min_karma=20,
        self_promo_ratio=0.1,
        notes="실무 도구 중심. 가벼운 프로젝트 반감.",
    ),
    "coolgithubprojects": SubredditProfile(
        name="coolgithubprojects",
        min_karma=5,
        self_promo_allowed=True,
        self_promo_ratio=1.0,
        notes="GitHub 프로젝트 공유 전용. 링크 필수.",
    ),
    "selfhosted": SubredditProfile(
        name="selfhosted",
        min_karma=10,
        notes="셀프호스팅 가능해야. Docker/서버 배포 관련.",
    ),
}


@dataclass
class RuleCheckResult:
    allowed: bool
    warnings: list[str]
    blocks: list[str]


def check_rules(subreddit: str, action_type: str, is_self_promo: bool = False) -> RuleCheckResult:
    """서브레딧 규칙 체크."""
    sub = subreddit.replace("r/", "").lower()
    profile = PROFILES.get(sub)

    warnings = []
    blocks = []

    if not profile:
        warnings.append(f"r/{sub}: 프로필 미등록 — 기본 규칙 적용")
        return RuleCheckResult(allowed=True, warnings=warnings, blocks=blocks)

    # 셀프 프로모 체크
    if is_self_promo and not profile.self_promo_allowed:
        blocks.append(f"r/{sub}: 자기 홍보 금지 서브레딧")

    if is_self_promo and profile.self_promo_ratio < 0.2:
        warnings.append(
            f"r/{sub}: 10:1 규칙 — 홍보 전 기여 댓글 {int(1/profile.self_promo_ratio)}개 필요"
        )

    # 포스트 타입
    if action_type == "post" and "text" not in profile.allowed_types:
        blocks.append(f"r/{sub}: 텍스트 포스트 미허용")

    # 참고사항
    if profile.notes:
        warnings.append(f"r/{sub} 참고: {profile.notes}")

    allowed = len(blocks) == 0
    return RuleCheckResult(allowed=allowed, warnings=warnings, blocks=blocks)


def get_profile(subreddit: str) -> SubredditProfile | None:
    """서브레딧 프로필 조회."""
    sub = subreddit.replace("r/", "").lower()
    return PROFILES.get(sub)
