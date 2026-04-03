"""30일 전략 스케줄 — 카르마 빌딩 우선, 점진적 활동 확대.

기존 마크다운 파일 의존 없이 프로그래밍 방식으로 전략 관리.
Phase 1: 카르마 빌딩 (앱 언급 없이)
Phase 2: 카르마 + 가벼운 씨뿌리기
Phase 3: 씨뿌리기 + 첫 포스트
Phase 4: 본격 캠페인

campaign.toml이 있으면 config 기반, 없으면 기본 하드코딩 서브레딧 사용.
DB에 커스텀 스케줄이 있으면 자동 생성된 스케줄보다 우선 적용.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum


class Phase(Enum):
    KARMA_BUILD = "karma_build"       # 순수 카르마 빌딩
    LIGHT_SEED = "light_seed"         # 카르마 + 가벼운 씨뿌리기
    SEED_AND_POST = "seed_and_post"   # 씨뿌리기 + 포스팅
    FULL_CAMPAIGN = "full_campaign"   # 전체 캠페인


class TaskType(Enum):
    KARMA_COMMENT = "karma_comment"   # 앱 무관 도움 댓글
    SEED_COMMENT = "seed_comment"     # 자연스러운 앱 언급 댓글
    POST = "post"                     # 서브레딧 포스트
    MONITOR = "monitor"              # 기존 포스트 모니터링
    REST = "rest"                     # 휴식
    REVIEW = "review"                # 성과 분석


@dataclass
class DayTask:
    task_type: TaskType
    subreddits: list[str] = field(default_factory=list)
    search_keywords: list[str] = field(default_factory=list)
    max_comments: int = 0
    post_subreddit: str = ""
    notes: str = ""


@dataclass
class DaySchedule:
    day: int
    phase: Phase
    tasks: list[DayTask] = field(default_factory=list)
    description: str = ""


# 카르마 빌딩용 서브레딧 + 키워드
KARMA_SUBS = {
    "commandline": ["terminal workflow", "cli tools", "shell productivity", "zsh fish bash"],
    "programming": ["developer tools", "code editor", "productivity tips", "IDE setup"],
    "webdev": ["frontend tools", "developer experience", "web tooling"],
    "linux": ["terminal emulator", "desktop linux", "window manager"],
    "vim": ["terminal multiplexer", "vim workflow", "neovim setup"],
    "neovim": ["terminal integration", "plugin", "lua config"],
    "rust": ["tauri app", "cross-platform", "wasm"],
    "devops": ["monitoring", "deployment tools", "CI/CD"],
    "python": ["cli framework", "automation", "scripting"],
    "golang": ["developer tools", "cli apps"],
    "opensource": ["new project", "side project", "open source tools"],
    "selfhosted": ["self-hosted tools", "server dashboard"],
}

# 씨뿌리기 타겟 (앱과 관련된 서브레딧)
SEED_SUBS = {
    "commandline": ["terminal multiplexer", "terminal tabs", "tmux alternative"],
    "webdev": ["developer terminal", "web dev tools", "terminal setup"],
    "programming": ["terminal tools", "developer workflow", "multi-language IDE"],
    "rust": ["tauri desktop app", "rust gui", "cross-platform"],
    "SideProject": ["weekend project", "indie dev", "show my project"],
    "macapps": ["mac terminal", "mac developer tools"],
    "coolgithubprojects": ["github project", "open source tool"],
    "opensource": ["terminal emulator", "developer tools"],
}

# 포스팅 서브레딧 순서 (점진적으로)
POST_ORDER = [
    # Phase 3: 작은 서브부터
    {"sub": "SideProject", "title_hint": "Show: 터미널 앱 공유"},
    {"sub": "coolgithubprojects", "title_hint": "GitHub 프로젝트 공유"},
    # Phase 4: 중간 규모
    {"sub": "commandline", "title_hint": "CLI 워크플로우 향상"},
    {"sub": "rust", "title_hint": "Tauri 기반 터미널"},
    {"sub": "macapps", "title_hint": "Mac 터미널 앱"},
    {"sub": "webdev", "title_hint": "개발자 터미널 도구"},
    {"sub": "programming", "title_hint": "개발 도구 소개"},
    {"sub": "linux", "title_hint": "크로스플랫폼 터미널"},
    {"sub": "opensource", "title_hint": "오픈소스 터미널"},
    {"sub": "selfhosted", "title_hint": "셀프호스트 터미널"},
    {"sub": "devops", "title_hint": "DevOps 터미널 도구"},
    {"sub": "neovim", "title_hint": "Neovim 통합 터미널"},
    {"sub": "vim", "title_hint": "Vim 워크플로우"},
]


# 캠페인 전체 날짜 순서 (공유 상수)
DAY_ORDER = [
    "prep-d3", "prep-d2", "prep-d1",
    *[f"day-{i:02d}" for i in range(1, 31)],
]


def build_schedule() -> list[DaySchedule]:
    """30일 전체 스케줄 생성."""
    schedule = []

    # ═══ Phase 1: Days 1-7 — 순수 카르마 빌딩 ═══
    karma_subs_list = list(KARMA_SUBS.keys())

    for day in range(1, 8):
        if day == 7:
            # Day 7: 휴식 + 리뷰
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.KARMA_BUILD,
                tasks=[DayTask(task_type=TaskType.REVIEW, notes="1주차 카르마 빌딩 성과 분석")],
                description="1주차 리뷰 — 카르마 현황 확인",
            ))
        else:
            # 하루 2-3개 서브레딧에서 도움 댓글
            subs_for_day = karma_subs_list[(day - 1) * 2: (day - 1) * 2 + 3]
            if not subs_for_day:
                subs_for_day = karma_subs_list[:2]

            tasks = []
            for sub in subs_for_day:
                keywords = KARMA_SUBS.get(sub, ["developer tools"])
                tasks.append(DayTask(
                    task_type=TaskType.KARMA_COMMENT,
                    subreddits=[sub],
                    search_keywords=keywords,
                    max_comments=2,
                    notes=f"r/{sub}에서 도움 댓글 (앱 언급 금지)",
                ))
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.KARMA_BUILD,
                tasks=tasks,
                description=f"카르마 빌딩: {', '.join(subs_for_day)}",
            ))

    # ═══ Phase 2: Days 8-14 — 카르마 + 가벼운 씨뿌리기 ═══
    seed_subs_list = list(SEED_SUBS.keys())

    for day in range(8, 15):
        if day == 13:
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.LIGHT_SEED,
                tasks=[DayTask(task_type=TaskType.REST, notes="휴식")],
                description="휴식일",
            ))
        elif day == 14:
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.LIGHT_SEED,
                tasks=[
                    DayTask(task_type=TaskType.REVIEW, notes="2주차 성과 분석"),
                    DayTask(task_type=TaskType.MONITOR, notes="기존 활동 반응 확인"),
                ],
                description="2주차 리뷰",
            ))
        else:
            tasks = []
            # 카르마 빌딩 1-2개
            karma_idx = (day - 8) % len(karma_subs_list)
            karma_sub = karma_subs_list[karma_idx]
            tasks.append(DayTask(
                task_type=TaskType.KARMA_COMMENT,
                subreddits=[karma_sub],
                search_keywords=KARMA_SUBS[karma_sub],
                max_comments=2,
                notes=f"카르마: r/{karma_sub}",
            ))

            # 씨뿌리기 1개 (자연스럽게)
            seed_idx = (day - 8) % len(seed_subs_list)
            seed_sub = seed_subs_list[seed_idx]
            tasks.append(DayTask(
                task_type=TaskType.SEED_COMMENT,
                subreddits=[seed_sub],
                search_keywords=SEED_SUBS[seed_sub],
                max_comments=1,
                notes=f"씨뿌리기: r/{seed_sub} (자연스러운 언급)",
            ))

            schedule.append(DaySchedule(
                day=day,
                phase=Phase.LIGHT_SEED,
                tasks=tasks,
                description=f"카르마({karma_sub}) + 씨뿌리기({seed_sub})",
            ))

    # ═══ Phase 3: Days 15-21 — 씨뿌리기 + 첫 포스트 ═══
    post_idx = 0

    for day in range(15, 22):
        if day == 20:
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.SEED_AND_POST,
                tasks=[DayTask(task_type=TaskType.REST, notes="휴식")],
                description="휴식일",
            ))
        elif day == 21:
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.SEED_AND_POST,
                tasks=[
                    DayTask(task_type=TaskType.REVIEW, notes="3주차 성과 분석 + 포스트 반응"),
                    DayTask(task_type=TaskType.MONITOR, notes="포스트 모니터링"),
                ],
                description="3주차 리뷰",
            ))
        elif day in (16, 19):
            # 포스트 날 — 작은 서브부터
            tasks = []
            if post_idx < len(POST_ORDER):
                post_info = POST_ORDER[post_idx]
                tasks.append(DayTask(
                    task_type=TaskType.POST,
                    post_subreddit=post_info["sub"],
                    notes=post_info["title_hint"],
                ))
                post_idx += 1

            # 씨뿌리기도 병행
            seed_idx = (day - 15) % len(seed_subs_list)
            seed_sub = seed_subs_list[seed_idx]
            tasks.append(DayTask(
                task_type=TaskType.SEED_COMMENT,
                subreddits=[seed_sub],
                search_keywords=SEED_SUBS[seed_sub],
                max_comments=2,
                notes=f"씨뿌리기: r/{seed_sub}",
            ))

            schedule.append(DaySchedule(
                day=day,
                phase=Phase.SEED_AND_POST,
                tasks=tasks,
                description=f"포스트({post_info['sub']}) + 씨뿌리기",
            ))
        else:
            # 씨뿌리기 + 카르마
            tasks = []
            seed_idx = (day - 15) % len(seed_subs_list)
            seed_sub = seed_subs_list[seed_idx]
            tasks.append(DayTask(
                task_type=TaskType.SEED_COMMENT,
                subreddits=[seed_sub],
                search_keywords=SEED_SUBS[seed_sub],
                max_comments=2,
            ))
            tasks.append(DayTask(
                task_type=TaskType.MONITOR,
                notes="기존 포스트 반응 확인",
            ))
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.SEED_AND_POST,
                tasks=tasks,
                description=f"씨뿌리기({seed_sub}) + 모니터링",
            ))

    # ═══ Phase 4: Days 22-30 — 본격 캠페인 ═══
    for day in range(22, 31):
        if day == 27:
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.FULL_CAMPAIGN,
                tasks=[DayTask(task_type=TaskType.REST, notes="휴식")],
                description="휴식일",
            ))
        elif day == 28:
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.FULL_CAMPAIGN,
                tasks=[
                    DayTask(task_type=TaskType.REVIEW, notes="4주차 + 전체 성과 분석"),
                    DayTask(task_type=TaskType.MONITOR, notes="모든 포스트 모니터링"),
                ],
                description="4주차 리뷰",
            ))
        elif day == 30:
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.FULL_CAMPAIGN,
                tasks=[
                    DayTask(task_type=TaskType.REVIEW, notes="최종 성과 분석 + ROI 보고서"),
                    DayTask(task_type=TaskType.MONITOR, notes="전체 포스트 최종 모니터링"),
                ],
                description="최종 리뷰 + ROI",
            ))
        elif day in (22, 24, 26, 29):
            # 포스트 날
            tasks = []
            if post_idx < len(POST_ORDER):
                post_info = POST_ORDER[post_idx]
                tasks.append(DayTask(
                    task_type=TaskType.POST,
                    post_subreddit=post_info["sub"],
                    notes=post_info["title_hint"],
                ))
                post_idx += 1

            # 씨뿌리기 2개
            for i in range(2):
                s_idx = ((day - 22) * 2 + i) % len(seed_subs_list)
                s_sub = seed_subs_list[s_idx]
                tasks.append(DayTask(
                    task_type=TaskType.SEED_COMMENT,
                    subreddits=[s_sub],
                    search_keywords=SEED_SUBS[s_sub],
                    max_comments=2,
                ))

            schedule.append(DaySchedule(
                day=day,
                phase=Phase.FULL_CAMPAIGN,
                tasks=tasks,
                description=f"포스트 + 씨뿌리기",
            ))
        else:
            # 댓글 관리 + 씨뿌리기
            tasks = []
            tasks.append(DayTask(
                task_type=TaskType.MONITOR,
                notes="포스트 댓글 응답",
            ))
            s_idx = (day - 22) % len(seed_subs_list)
            s_sub = seed_subs_list[s_idx]
            tasks.append(DayTask(
                task_type=TaskType.SEED_COMMENT,
                subreddits=[s_sub],
                search_keywords=SEED_SUBS[s_sub],
                max_comments=2,
            ))
            tasks.append(DayTask(
                task_type=TaskType.KARMA_COMMENT,
                subreddits=[karma_subs_list[(day - 22) % len(karma_subs_list)]],
                search_keywords=KARMA_SUBS[karma_subs_list[(day - 22) % len(karma_subs_list)]],
                max_comments=1,
            ))
            schedule.append(DaySchedule(
                day=day,
                phase=Phase.FULL_CAMPAIGN,
                tasks=tasks,
                description=f"모니터링 + 씨뿌리기 + 카르마",
            ))

    return schedule


def build_schedule_from_config(config) -> list[DaySchedule]:
    """CampaignConfig 기반 30일 스케줄 생성."""
    schedule = []

    karma_subs = {st.sub: st.keywords for st in config.karma_subs} if config.karma_subs else KARMA_SUBS
    seed_subs = {st.sub: st.keywords for st in config.seed_subs} if config.seed_subs else SEED_SUBS
    post_order = (
        [{"sub": pt.sub, "title_hint": pt.title_hint} for pt in config.post_subs]
        if config.post_subs else POST_ORDER
    )

    karma_subs_list = list(karma_subs.keys())
    seed_subs_list = list(seed_subs.keys())

    # Phase 1: Days 1-7 — 카르마 빌딩
    for day in range(1, 8):
        if day == 7:
            schedule.append(DaySchedule(
                day=day, phase=Phase.KARMA_BUILD,
                tasks=[DayTask(task_type=TaskType.REVIEW, notes="1주차 카르마 빌딩 성과 분석")],
                description="1주차 리뷰 — 카르마 현황 확인",
            ))
        else:
            subs_for_day = karma_subs_list[(day - 1) * 2: (day - 1) * 2 + 3]
            if not subs_for_day:
                subs_for_day = karma_subs_list[:2]
            tasks = []
            for sub in subs_for_day:
                keywords = karma_subs.get(sub, ["developer tools"])
                if isinstance(keywords, list):
                    kw = keywords
                else:
                    kw = [keywords]
                tasks.append(DayTask(
                    task_type=TaskType.KARMA_COMMENT,
                    subreddits=[sub], search_keywords=kw, max_comments=2,
                    notes=f"r/{sub}에서 도움 댓글 (앱 언급 금지)",
                ))
            schedule.append(DaySchedule(
                day=day, phase=Phase.KARMA_BUILD, tasks=tasks,
                description=f"카르마 빌딩: {', '.join(subs_for_day)}",
            ))

    # Phase 2: Days 8-14 — 카르마 + 씨뿌리기
    for day in range(8, 15):
        if day == 13:
            schedule.append(DaySchedule(
                day=day, phase=Phase.LIGHT_SEED,
                tasks=[DayTask(task_type=TaskType.REST, notes="휴식")],
                description="휴식일",
            ))
        elif day == 14:
            schedule.append(DaySchedule(
                day=day, phase=Phase.LIGHT_SEED,
                tasks=[
                    DayTask(task_type=TaskType.REVIEW, notes="2주차 성과 분석"),
                    DayTask(task_type=TaskType.MONITOR, notes="기존 활동 반응 확인"),
                ],
                description="2주차 리뷰",
            ))
        else:
            tasks = []
            karma_idx = (day - 8) % len(karma_subs_list)
            karma_sub = karma_subs_list[karma_idx]
            tasks.append(DayTask(
                task_type=TaskType.KARMA_COMMENT,
                subreddits=[karma_sub],
                search_keywords=karma_subs.get(karma_sub, ["developer tools"]),
                max_comments=2,
                notes=f"카르마: r/{karma_sub}",
            ))
            seed_idx = (day - 8) % len(seed_subs_list)
            seed_sub = seed_subs_list[seed_idx]
            tasks.append(DayTask(
                task_type=TaskType.SEED_COMMENT,
                subreddits=[seed_sub],
                search_keywords=seed_subs.get(seed_sub, ["tool"]),
                max_comments=1,
                notes=f"씨뿌리기: r/{seed_sub} (자연스러운 언급)",
            ))
            schedule.append(DaySchedule(
                day=day, phase=Phase.LIGHT_SEED, tasks=tasks,
                description=f"카르마({karma_sub}) + 씨뿌리기({seed_sub})",
            ))

    # Phase 3: Days 15-21 — 씨뿌리기 + 포스트
    post_idx = 0
    for day in range(15, 22):
        if day == 20:
            schedule.append(DaySchedule(
                day=day, phase=Phase.SEED_AND_POST,
                tasks=[DayTask(task_type=TaskType.REST, notes="휴식")],
                description="휴식일",
            ))
        elif day == 21:
            schedule.append(DaySchedule(
                day=day, phase=Phase.SEED_AND_POST,
                tasks=[
                    DayTask(task_type=TaskType.REVIEW, notes="3주차 성과 분석 + 포스트 반응"),
                    DayTask(task_type=TaskType.MONITOR, notes="포스트 모니터링"),
                ],
                description="3주차 리뷰",
            ))
        elif day in (16, 19):
            tasks = []
            if post_idx < len(post_order):
                post_info = post_order[post_idx]
                tasks.append(DayTask(
                    task_type=TaskType.POST,
                    post_subreddit=post_info["sub"],
                    notes=post_info.get("title_hint", ""),
                ))
                post_idx += 1
            seed_idx = (day - 15) % len(seed_subs_list)
            seed_sub = seed_subs_list[seed_idx]
            tasks.append(DayTask(
                task_type=TaskType.SEED_COMMENT,
                subreddits=[seed_sub],
                search_keywords=seed_subs.get(seed_sub, ["tool"]),
                max_comments=2,
                notes=f"씨뿌리기: r/{seed_sub}",
            ))
            schedule.append(DaySchedule(
                day=day, phase=Phase.SEED_AND_POST, tasks=tasks,
                description=f"포스트({post_order[post_idx-1]['sub'] if post_idx > 0 else '?'}) + 씨뿌리기",
            ))
        else:
            tasks = []
            seed_idx = (day - 15) % len(seed_subs_list)
            seed_sub = seed_subs_list[seed_idx]
            tasks.append(DayTask(
                task_type=TaskType.SEED_COMMENT,
                subreddits=[seed_sub],
                search_keywords=seed_subs.get(seed_sub, ["tool"]),
                max_comments=2,
            ))
            tasks.append(DayTask(
                task_type=TaskType.MONITOR, notes="기존 포스트 반응 확인",
            ))
            schedule.append(DaySchedule(
                day=day, phase=Phase.SEED_AND_POST, tasks=tasks,
                description=f"씨뿌리기({seed_sub}) + 모니터링",
            ))

    # Phase 4: Days 22-30 — 본격 캠페인
    for day in range(22, 31):
        if day == 27:
            schedule.append(DaySchedule(
                day=day, phase=Phase.FULL_CAMPAIGN,
                tasks=[DayTask(task_type=TaskType.REST, notes="휴식")],
                description="휴식일",
            ))
        elif day == 28:
            schedule.append(DaySchedule(
                day=day, phase=Phase.FULL_CAMPAIGN,
                tasks=[
                    DayTask(task_type=TaskType.REVIEW, notes="4주차 + 전체 성과 분석"),
                    DayTask(task_type=TaskType.MONITOR, notes="모든 포스트 모니터링"),
                ],
                description="4주차 리뷰",
            ))
        elif day == 30:
            schedule.append(DaySchedule(
                day=day, phase=Phase.FULL_CAMPAIGN,
                tasks=[
                    DayTask(task_type=TaskType.REVIEW, notes="최종 성과 분석 + ROI 보고서"),
                    DayTask(task_type=TaskType.MONITOR, notes="전체 포스트 최종 모니터링"),
                ],
                description="최종 리뷰 + ROI",
            ))
        elif day in (22, 24, 26, 29):
            tasks = []
            if post_idx < len(post_order):
                post_info = post_order[post_idx]
                tasks.append(DayTask(
                    task_type=TaskType.POST,
                    post_subreddit=post_info["sub"],
                    notes=post_info.get("title_hint", ""),
                ))
                post_idx += 1
            for i in range(2):
                s_idx = ((day - 22) * 2 + i) % len(seed_subs_list)
                s_sub = seed_subs_list[s_idx]
                tasks.append(DayTask(
                    task_type=TaskType.SEED_COMMENT,
                    subreddits=[s_sub],
                    search_keywords=seed_subs.get(s_sub, ["tool"]),
                    max_comments=2,
                ))
            schedule.append(DaySchedule(
                day=day, phase=Phase.FULL_CAMPAIGN, tasks=tasks,
                description="포스트 + 씨뿌리기",
            ))
        else:
            tasks = []
            tasks.append(DayTask(
                task_type=TaskType.MONITOR, notes="포스트 댓글 응답",
            ))
            s_idx = (day - 22) % len(seed_subs_list)
            s_sub = seed_subs_list[s_idx]
            tasks.append(DayTask(
                task_type=TaskType.SEED_COMMENT,
                subreddits=[s_sub],
                search_keywords=seed_subs.get(s_sub, ["tool"]),
                max_comments=2,
            ))
            tasks.append(DayTask(
                task_type=TaskType.KARMA_COMMENT,
                subreddits=[karma_subs_list[(day - 22) % len(karma_subs_list)]],
                search_keywords=karma_subs.get(
                    karma_subs_list[(day - 22) % len(karma_subs_list)],
                    ["developer tools"]
                ),
                max_comments=1,
            ))
            schedule.append(DaySchedule(
                day=day, phase=Phase.FULL_CAMPAIGN, tasks=tasks,
                description="모니터링 + 씨뿌리기 + 카르마",
            ))

    return schedule


def get_day_schedule(day: int, config=None) -> DaySchedule | None:
    """특정 날의 스케줄 반환."""
    sched = build_schedule_from_config(config) if config else build_schedule()
    for s in sched:
        if s.day == day:
            return s
    return None


def format_schedule_overview(config=None) -> str:
    """30일 전체 스케줄 개요."""
    schedule = build_schedule_from_config(config) if config else build_schedule()
    lines = ["═══ 30-Day Campaign Schedule ═══", ""]

    if config:
        lines.append(f"  Product: {config.product_name}")
        lines.append(f"  URL: {config.product_url}")
        lines.append("")

    current_phase = None
    for s in schedule:
        if s.phase != current_phase:
            current_phase = s.phase
            phase_names = {
                Phase.KARMA_BUILD: "Phase 1: 카르마 빌딩 (앱 언급 없이)",
                Phase.LIGHT_SEED: "Phase 2: 카르마 + 가벼운 씨뿌리기",
                Phase.SEED_AND_POST: "Phase 3: 씨뿌리기 + 첫 포스트",
                Phase.FULL_CAMPAIGN: "Phase 4: 본격 캠페인",
            }
            lines.append(f"\n── {phase_names[current_phase]} ──")

        task_icons = {
            TaskType.KARMA_COMMENT: "K",
            TaskType.SEED_COMMENT: "S",
            TaskType.POST: "P",
            TaskType.MONITOR: "M",
            TaskType.REST: "R",
            TaskType.REVIEW: "V",
        }
        task_types = [t.task_type for t in s.tasks]
        icons = " ".join(task_icons.get(t, "?") for t in task_types)
        lines.append(f"  Day {s.day:2d} | {icons} | {s.description}")

    return "\n".join(lines)


# ═══ 커스텀 스케줄: DB에 저장된 사용자 편집 스케줄 ═══

def _task_to_dict(task: DayTask) -> dict:
    return {
        "type": task.task_type.value,
        "subreddits": task.subreddits,
        "keywords": task.search_keywords,
        "max_comments": task.max_comments,
        "post_subreddit": task.post_subreddit,
        "notes": task.notes,
    }


def _dict_to_task(d: dict) -> DayTask:
    type_val = d.get("type") or d.get("task_type")
    keywords = d.get("keywords") or d.get("search_keywords", [])
    return DayTask(
        task_type=TaskType(type_val),
        subreddits=d.get("subreddits", []),
        search_keywords=keywords,
        max_comments=d.get("max_comments", 0),
        post_subreddit=d.get("post_subreddit", ""),
        notes=d.get("notes", ""),
    )


def day_schedule_to_dict(s: DaySchedule) -> dict:
    return {
        "day": s.day,
        "phase": s.phase.value,
        "description": s.description,
        "tasks": [_task_to_dict(t) for t in s.tasks],
    }


def dict_to_day_schedule(d: dict) -> DaySchedule:
    return DaySchedule(
        day=d["day"],
        phase=Phase(d["phase"]),
        tasks=[_dict_to_task(t) for t in d.get("tasks", [])],
        description=d.get("description", ""),
    )


def save_schedule_to_db(db, schedule: list[DaySchedule]):
    """전체 스케줄을 DB에 저장."""
    for s in schedule:
        tasks_json = json.dumps([_task_to_dict(t) for t in s.tasks], ensure_ascii=False)
        db.save_custom_schedule(s.day, s.phase.value, s.description, tasks_json)


def load_schedule_from_db(db) -> list[DaySchedule]:
    """DB에서 커스텀 스케줄 로드."""
    rows = db.get_all_custom_schedules()
    result = []
    for row in rows:
        tasks = json.loads(row["tasks_json"]) if row.get("tasks_json") else []
        result.append(DaySchedule(
            day=row["day"],
            phase=Phase(row["phase"]),
            tasks=[_dict_to_task(t) for t in tasks],
            description=row.get("description", ""),
        ))
    return result


def get_effective_schedule(config=None, db=None) -> list[DaySchedule]:
    """최종 스케줄: DB 커스텀 > config 기반 > 기본.

    DB에 저장된 날은 커스텀 사용, 없는 날은 자동 생성.
    """
    # 자동 생성 스케줄
    if config:
        auto = build_schedule_from_config(config)
    else:
        auto = build_schedule()

    if not db:
        return auto

    # DB 커스텀 스케줄 로드
    custom_rows = db.get_all_custom_schedules()
    if not custom_rows:
        return auto

    custom_map = {}
    for row in custom_rows:
        tasks = json.loads(row["tasks_json"]) if row.get("tasks_json") else []
        custom_map[row["day"]] = DaySchedule(
            day=row["day"],
            phase=Phase(row["phase"]),
            tasks=[_dict_to_task(t) for t in tasks],
            description=row.get("description", ""),
        )

    # 합성: 커스텀이 있으면 커스텀, 없으면 자동
    result = []
    for s in auto:
        if s.day in custom_map:
            result.append(custom_map[s.day])
        else:
            result.append(s)
    return result
