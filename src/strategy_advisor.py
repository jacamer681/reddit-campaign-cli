"""전략 어드바이저 — DB 데이터 분석 → 마케팅 전략 자동 수립.

매일 활동 데이터를 분석하고:
1. 카르마 트렌드 파악
2. 서브레딧별 ROI 분석
3. 활동 패턴 최적화 제안
4. 다음 날 전략 수립
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .marketing.account_health import check_health
from .marketing.anti_spam import get_daily_budget
from .marketing.performance import get_subreddit_rankings, suggest_effort_reallocation
from .state import StateDB


def generate_daily_report(db: StateDB, karma: int = 0) -> dict:
    """매일 종합 리포트 생성 + DB 저장."""
    today = datetime.now().strftime("%Y-%m-%d")
    summary = db.get_activity_summary(today)

    # 카르마 변화량
    prev_karma = db.get_latest_karma()
    karma_change = karma - prev_karma if karma > 0 and prev_karma > 0 else 0

    # 카르마 기록
    if karma > 0:
        db.save_karma(karma)

    # 최다 활동 서브레딧
    top_sub = ""
    if summary["comments_by_sub"]:
        top_sub = summary["comments_by_sub"][0]["subreddit"]

    # 건강도
    health = check_health(db)

    # 전략 노트 생성
    notes = _build_strategy_notes(db, summary, karma, karma_change, health)

    # 저장
    db.save_daily_report(
        report_date=today,
        karma=karma,
        karma_change=karma_change,
        comments_count=summary["comments_total"],
        posts_count=summary["posts_total"],
        upvotes_count=summary["upvotes_total"],
        browsed_count=summary["browsed_total"],
        top_subreddit=top_sub,
        risk_level=health.risk_level.value,
        strategy_notes=notes,
    )

    return {
        "date": today,
        "karma": karma,
        "karma_change": karma_change,
        "comments": summary["comments_total"],
        "posts": summary["posts_total"],
        "upvotes": summary["upvotes_total"],
        "browsed": summary["browsed_total"],
        "top_subreddit": top_sub,
        "risk_level": health.risk_level.value,
        "strategy": notes,
    }


def _build_strategy_notes(db, summary, karma, karma_change, health) -> str:
    """오늘 활동 기반 전략 노트."""
    lines = []

    # 카르마 트렌드
    if karma_change > 0:
        lines.append(f"카르마 +{karma_change} 상승")
    elif karma_change < 0:
        lines.append(f"카르마 {karma_change} 하락 — 댓글 톤 점검 필요")

    # 활동량 분석
    comments = summary["comments_total"]
    if comments == 0:
        lines.append("오늘 댓글 0 — 최소 3개 카르마 빌딩 필요")
    elif comments < 3:
        lines.append(f"댓글 {comments}개 — 목표 5개")
    elif comments >= 8:
        lines.append(f"댓글 {comments}개 — 오늘은 충분, 내일 줄여도 됨")

    # 건강도
    if health.risk_level.value == "red":
        lines.append("계정 위험! 24시간 휴식 권장")
    elif health.risk_level.value == "yellow":
        lines.append("계정 주의 — 활동 속도 줄이기")

    return " | ".join(lines) if lines else "정상 활동"


def suggest_next_day_strategy(db: StateDB) -> list[dict]:
    """내일 마케팅 전략 제안 (DB 분석 기반)."""
    strategies = []
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. 카르마 트렌드 분석
    karma_history = db.get_karma_history(7)
    if len(karma_history) >= 2:
        recent = karma_history[0]["karma"]
        older = karma_history[-1]["karma"]
        trend = recent - older

        if trend < 0:
            s = {
                "type": "karma_recovery",
                "recommendation": "카르마 회복 모드 — 도움 댓글 위주",
                "reason": f"최근 7일 카르마 {trend} 하락",
                "priority": 10,
                "subreddits": ["commandline", "programming", "python"],
            }
            strategies.append(s)
            db.save_strategy("karma_recovery", "", s["recommendation"], s["reason"], 10)
        elif trend > 50:
            s = {
                "type": "expand",
                "recommendation": "카르마 충분 — 씨뿌리기 확대 가능",
                "reason": f"최근 7일 카르마 +{trend} 상승",
                "priority": 5,
                "subreddits": [],
            }
            strategies.append(s)
            db.save_strategy("expand", "", s["recommendation"], s["reason"], 5)

    # 2. 서브레딧별 ROI 분석
    rankings = get_subreddit_rankings(db)
    realloc = suggest_effort_reallocation(rankings)

    for sub, action in realloc.items():
        if action == "increase":
            s = {
                "type": "increase_effort",
                "recommendation": f"r/{sub} 활동 증가 — ROI 높음",
                "reason": f"ROI 스코어 상위",
                "priority": 7,
                "subreddits": [sub],
            }
            strategies.append(s)
            db.save_strategy("increase_effort", sub, s["recommendation"], s["reason"], 7)
        elif action == "stop":
            s = {
                "type": "stop_effort",
                "recommendation": f"r/{sub} 활동 중단 검토 — ROI 낮음",
                "reason": f"노력 대비 성과 부족",
                "priority": 3,
                "subreddits": [sub],
            }
            strategies.append(s)
            db.save_strategy("stop_effort", sub, s["recommendation"], s["reason"], 3)

    # 3. 활동 패턴 분석
    reports = db.get_daily_reports(7)
    if reports:
        avg_comments = sum(r["comments_count"] for r in reports) / len(reports)
        if avg_comments < 2:
            s = {
                "type": "increase_activity",
                "recommendation": "일일 댓글 수 증가 필요 (목표: 5개/일)",
                "reason": f"최근 7일 평균 {avg_comments:.1f}개/일",
                "priority": 8,
                "subreddits": [],
            }
            strategies.append(s)
            db.save_strategy("increase_activity", "", s["recommendation"], s["reason"], 8)

    # 4. 서브레딧 다양성 체크
    summary = db.get_activity_summary()
    if summary["comments_by_sub"]:
        total = sum(r["cnt"] for r in summary["comments_by_sub"])
        top = summary["comments_by_sub"][0]
        if total > 5 and top["cnt"] / total > 0.5:
            s = {
                "type": "diversify",
                "recommendation": f"서브레딧 다양화 필요 — r/{top['subreddit']}에 집중됨",
                "reason": f"전체 댓글의 {top['cnt']*100//total}%가 한 곳",
                "priority": 6,
                "subreddits": [],
            }
            strategies.append(s)
            db.save_strategy("diversify", top["subreddit"], s["recommendation"], s["reason"], 6)

    # 5. 예산 확인
    budget = get_daily_budget(db)
    if not budget.can_post and not budget.can_comment:
        s = {
            "type": "rest",
            "recommendation": "오늘은 휴식 — 예산 소진",
            "reason": "일일 포스트/댓글 한도 도달",
            "priority": 10,
            "subreddits": [],
        }
        strategies.append(s)

    strategies.sort(key=lambda x: x["priority"], reverse=True)
    return strategies


def format_strategy_report(strategies: list[dict]) -> str:
    """전략 리포트 텍스트 포맷."""
    if not strategies:
        return "전략 제안 없음 — 현재 계획 유지"

    lines = ["=== 마케팅 전략 제안 ===", ""]
    for i, s in enumerate(strategies, 1):
        priority_icon = "!!!" if s["priority"] >= 8 else "!!" if s["priority"] >= 5 else "!"
        lines.append(f"{i}. [{priority_icon}] {s['recommendation']}")
        lines.append(f"   이유: {s['reason']}")
        if s.get("subreddits"):
            lines.append(f"   대상: {', '.join('r/' + sub for sub in s['subreddits'])}")
        lines.append("")

    return "\n".join(lines)
