"""포스팅 타이밍 최적화.

서브레딧별 최적 포스팅 시간 + 요일 판단.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum


class TimingGrade(Enum):
    OPTIMAL = "optimal"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    AVOID = "avoid"


@dataclass
class TimingAdvice:
    grade: TimingGrade
    reason: str
    next_optimal: datetime | None = None
    wait_seconds: int = 0


# EST = UTC-5 (미국 동부)
EST_OFFSET = timedelta(hours=-5)

# 서브레딧별 최적 시간 (EST 기준, hour range)
# (start_hour, end_hour, weekday_only)
PEAK_WINDOWS: dict[str, list[tuple[int, int, bool]]] = {
    "commandline": [(9, 12, True), (18, 21, True)],
    "programming": [(9, 11, True)],
    "rust": [(10, 13, True)],
    "ClaudeAI": [(9, 12, True), (14, 17, True)],
    "webdev": [(9, 12, True)],
    "SideProject": [(9, 12, True), (17, 20, True)],
    "macapps": [(10, 13, True)],
    "tauri": [(10, 13, True)],
    "neovim": [(10, 13, True), (19, 22, True)],
    "devops": [(9, 12, True)],
    "coolgithubprojects": [(9, 12, True)],
    "selfhosted": [(9, 12, True), (19, 22, True)],
}

# 기본 (등록 안 된 서브)
DEFAULT_PEAK = [(9, 12, True)]

# 피해야 할 시간대
AVOID_HOURS = list(range(0, 6))  # 0-6 AM EST

# 피해야 할 요일 (금요일 오후, 토요일)
AVOID_DAYS = {
    4: [(14, 24)],  # 금요일 오후
    5: [(0, 24)],   # 토요일 전체
}


def check_timing(subreddit: str, now: datetime | None = None) -> TimingAdvice:
    """현재 시간이 포스팅에 적합한지 판단."""
    if now is None:
        now = datetime.now(timezone.utc)

    # EST로 변환
    est_now = now + EST_OFFSET
    hour = est_now.hour
    weekday = est_now.weekday()  # 0=월 ~ 6=일

    sub = subreddit.replace("r/", "").lower()

    # 피해야 할 시간
    if hour in AVOID_HOURS:
        next_opt = _next_optimal_time(sub, est_now)
        return TimingAdvice(
            grade=TimingGrade.AVOID,
            reason=f"새벽 시간대 (EST {hour}시) — 트래픽 최저",
            next_optimal=next_opt,
            wait_seconds=_seconds_until(est_now, next_opt) if next_opt else 0,
        )

    # 피해야 할 요일
    if weekday in AVOID_DAYS:
        for start, end in AVOID_DAYS[weekday]:
            if start <= hour < end:
                next_opt = _next_optimal_time(sub, est_now)
                day_name = ["월", "화", "수", "목", "금", "토", "일"][weekday]
                return TimingAdvice(
                    grade=TimingGrade.POOR,
                    reason=f"{day_name}요일 — 주말 트래픽 저조",
                    next_optimal=next_opt,
                    wait_seconds=_seconds_until(est_now, next_opt) if next_opt else 0,
                )

    # 서브레딧별 최적 시간
    windows = PEAK_WINDOWS.get(sub, DEFAULT_PEAK)
    for start, end, weekday_only in windows:
        if weekday_only and weekday >= 5:
            continue
        if start <= hour < end:
            return TimingAdvice(
                grade=TimingGrade.OPTIMAL,
                reason=f"최적 시간대 (EST {hour}시, {sub})",
            )

    # 업무 시간이면 GOOD
    if 7 <= hour <= 22 and weekday < 5:
        return TimingAdvice(
            grade=TimingGrade.GOOD,
            reason=f"업무 시간대 (EST {hour}시)",
        )

    # 그 외
    if 7 <= hour <= 22:
        return TimingAdvice(
            grade=TimingGrade.ACCEPTABLE,
            reason=f"주말 낮 시간 (EST {hour}시)",
        )

    next_opt = _next_optimal_time(sub, est_now)
    return TimingAdvice(
        grade=TimingGrade.POOR,
        reason=f"비활동 시간대 (EST {hour}시)",
        next_optimal=next_opt,
        wait_seconds=_seconds_until(est_now, next_opt) if next_opt else 0,
    )


def _next_optimal_time(sub: str, est_now: datetime) -> datetime | None:
    """다음 최적 시간 계산."""
    windows = PEAK_WINDOWS.get(sub, DEFAULT_PEAK)
    hour = est_now.hour
    weekday = est_now.weekday()

    # 오늘 남은 윈도우
    for start, end, weekday_only in windows:
        if weekday_only and weekday >= 5:
            continue
        if hour < start:
            return est_now.replace(hour=start, minute=0, second=0, microsecond=0)

    # 다음 평일 첫 윈도우
    days_ahead = 1
    while days_ahead <= 3:
        next_day = est_now + timedelta(days=days_ahead)
        next_weekday = next_day.weekday()
        if next_weekday < 5:  # 평일
            first_start = windows[0][0] if windows else 9
            return next_day.replace(hour=first_start, minute=0, second=0, microsecond=0)
        days_ahead += 1

    return None


def _seconds_until(now: datetime, target: datetime) -> int:
    delta = target - now
    return max(0, int(delta.total_seconds()))
