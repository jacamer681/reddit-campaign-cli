"""Pi Browser + 마케팅 엔진 + 새 스케줄 통합 전자동 캠페인.

모든 액션은 마케팅 엔진의 pre_flight_check를 거침.
campaign.toml 기반 범용 캠페인 실행.
Phase 1->4 순서: 카르마 빌딩 -> 씨뿌리기 -> 포스팅.
"""

from __future__ import annotations

import random
import re
import time
from datetime import datetime
from pathlib import Path

from .display import console, show_error, show_info, show_success, show_warning
from .marketing.engine import MarketingEngine, Action, ActionType
from .schedule import (
    DaySchedule, DayTask, Phase, TaskType,
    build_schedule, build_schedule_from_config,
    get_day_schedule, format_schedule_overview,
)
from .pi_browser import RedditBrowser
from .state import StateDB

REPORT_DIR = "data/reports"


def _load_campaign_config():
    """campaign.toml 로드 (없으면 None)."""
    try:
        from .campaign_config import load_campaign, campaign_exists
        if campaign_exists():
            return load_campaign()
    except Exception as e:
        show_warning(f"campaign.toml 로드 실패: {e}")
    return None


def run_browser_campaign(
    db_path: str = "data/campaign.db",
    run_all: bool = False,
    dry_run: bool = False,
    delay: int = 30,
    comment_delay: int = 10,
    start_day: int | None = None,
    campaign_path: str | None = None,
    **kwargs,
):
    """새 스케줄 기반 전자동 캠페인."""
    db = StateDB(db_path)
    engine = MarketingEngine(db)

    # 캠페인 설정 로드
    campaign = None
    if campaign_path:
        from .campaign_config import load_campaign
        campaign = load_campaign(campaign_path)
    else:
        campaign = _load_campaign_config()

    if campaign:
        show_info(f"캠페인: {campaign.product_name} ({campaign.category})")
        if campaign.product_url:
            show_info(f"URL: {campaign.product_url}")

    # 상태 표시
    console.print()
    console.print(engine.format_status())
    console.print()

    # 건강도 체크
    health = engine.get_health()
    if not health.can_proceed and not dry_run:
        show_error("계정 위험 상태 - 활동 중단")
        for w in health.warnings:
            show_error(f"  {w}")
        db.close()
        return

    # 브라우저 연결
    browser = None
    if not dry_run:
        show_info("레딧브라우저 연결 중...")
        browser = RedditBrowser()
        if not browser.connect():
            show_error("레딧브라우저 연결 실패 - Chrome에서 레딧브라우저 확장 확인")
            db.close()
            return

        show_info("Reddit 로그인 확인...")
        login = browser.check_login()
        if login.get("logged_in"):
            show_success("Reddit 로그인 확인됨")
        else:
            show_warning("Reddit 미로그인 - Chrome에서 먼저 로그인하세요")
            db.close()
            return

    # 스케줄 생성 (config 기반 또는 기본)
    if campaign:
        schedule = build_schedule_from_config(campaign)
    else:
        schedule = build_schedule()

    # 시작 날짜 결정
    if start_day:
        schedule = [s for s in schedule if s.day >= start_day]
    else:
        for s in schedule:
            day_id = f"day-{s.day:02d}"
            status = db.get_day_status(day_id)
            if status not in ("completed",):
                schedule = [x for x in schedule if x.day >= s.day]
                break

    for day_schedule in schedule:
        day_id = f"day-{day_schedule.day:02d}"

        if db.get_day_status(day_id) == "completed":
            continue

        budget = engine.get_budget()
        console.print()
        console.print(f"  [bold]=== Day {day_schedule.day} - {day_schedule.phase.value} ===[/bold]")
        console.print(f"  {day_schedule.description}")
        console.print(f"  Posts: {budget.posts_used}/{budget.posts_limit} | "
                      f"Comments: {budget.comments_used}/{budget.comments_limit}")

        if dry_run:
            _dry_run_day(day_schedule, engine)
            db.set_day_status(day_id, "completed")
        else:
            _execute_day(browser, db, engine, day_schedule, campaign)

        _write_report(db, engine, day_schedule, campaign)

        if not run_all:
            break

        next_days = [s for s in schedule if s.day > day_schedule.day]
        if next_days and run_all:
            show_info(f"다음: Day {next_days[0].day} ({delay}초 후)...")
            time.sleep(delay)

    if not dry_run:
        _final_report(db, engine)

    db.close()
    if browser:
        browser.stop()


def _dry_run_day(day_schedule: DaySchedule, engine: MarketingEngine):
    """미리보기."""
    for task in day_schedule.tasks:
        icon = {
            TaskType.KARMA_COMMENT: "[cyan]KARMA[/cyan]",
            TaskType.SEED_COMMENT: "[green]SEED[/green]",
            TaskType.POST: "[yellow]POST[/yellow]",
            TaskType.MONITOR: "[blue]MONITOR[/blue]",
            TaskType.REST: "[dim]REST[/dim]",
            TaskType.REVIEW: "[magenta]REVIEW[/magenta]",
        }.get(task.task_type, "?")

        console.print(f"  {icon} {task.notes or task.task_type.value}")

        if task.subreddits:
            for sub in task.subreddits:
                action_type = (ActionType.KARMA_BUILD if task.task_type == TaskType.KARMA_COMMENT
                              else ActionType.SEEDING)
                action = Action(
                    action_type=action_type,
                    subreddit=sub,
                    body="[dry-run]",
                )
                pf = engine.pre_flight_check(action)
                status = "[green]OK[/green]" if pf.allowed else f"[red]BLOCKED: {', '.join(pf.blocks)}[/red]"
                console.print(f"    r/{sub}: {status}")
                if pf.warnings:
                    for w in pf.warnings:
                        console.print(f"      [yellow]! {w}[/yellow]")

        if task.task_type == TaskType.POST and task.post_subreddit:
            action = Action(
                action_type=ActionType.POST,
                subreddit=task.post_subreddit,
                title="[dry-run title]",
                body="[dry-run body]",
                is_self_promo=True,
            )
            pf = engine.pre_flight_check(action)
            status = "[green]OK[/green]" if pf.allowed else f"[red]BLOCKED: {', '.join(pf.blocks)}[/red]"
            console.print(f"    r/{task.post_subreddit}: {status}")

    show_success(f"  [DRY RUN] Day {day_schedule.day} 완료")


def _execute_day(browser: RedditBrowser, db: StateDB, engine: MarketingEngine,
                 day_schedule: DaySchedule, campaign=None):
    """실제 실행."""
    day_id = f"day-{day_schedule.day:02d}"
    db.set_day_status(day_id, "in_progress")

    try:
        for i, task in enumerate(day_schedule.tasks):
            if task.task_type == TaskType.KARMA_COMMENT:
                _exec_karma(browser, db, engine, task, campaign)
            elif task.task_type == TaskType.SEED_COMMENT:
                _exec_seed(browser, db, engine, task, campaign)
            elif task.task_type == TaskType.POST:
                _exec_post(browser, db, engine, task, campaign)
            elif task.task_type == TaskType.MONITOR:
                _exec_monitor(browser, db, engine)
            elif task.task_type == TaskType.REVIEW:
                _exec_review(db, engine)
            elif task.task_type == TaskType.REST:
                show_info("  휴식일 - 활동 없음")

            # 태스크 사이 대기 (마지막 태스크 제외)
            if i < len(day_schedule.tasks) - 1:
                between_delay = random.uniform(30, 60)
                show_info(f"  다음 태스크까지 {int(between_delay)}초 대기...")
                time.sleep(between_delay)

        db.set_day_status(day_id, "completed")
        show_success(f"  Day {day_schedule.day} 완료!")

    except Exception as e:
        show_error(f"  오류: {e}")
        db.set_day_status(day_id, "error")


def _get_random_delay(campaign=None) -> float:
    """봇 감지 회피용 랜덤 딜레이 — 최소 90초, 최대 180초.

    Reddit은 연속 댓글을 스팸으로 감지하므로 충분한 간격 필요.
    """
    base_min = 90
    base_max = 180
    if campaign:
        # config 값이 있어도 최소 90초 보장
        cfg_min = max(base_min, campaign.limits.min_delay_seconds)
        cfg_max = max(base_max, campaign.limits.max_delay_seconds)
        return random.uniform(cfg_min, cfg_max)
    return random.uniform(base_min, base_max)


def _check_daily_limit(db: StateDB, action_type: str, campaign=None) -> bool:
    """일일 한도 확인."""
    count = db.get_today_action_count(action_type)
    if campaign:
        if action_type == "karma_build":
            return count < campaign.limits.karma_comments_per_day
        elif action_type in ("seeding", "seed_comment"):
            return count < campaign.limits.seed_comments_per_day
    return count < 8  # 기본 한도


def _exec_karma(browser: RedditBrowser, db: StateDB, engine: MarketingEngine,
                task: DayTask, campaign=None):
    """카르마 빌딩 - 앱 언급 없이 도움 댓글."""
    for sub in task.subreddits:
        # 일일 한도 확인
        if not _check_daily_limit(db, "karma_build", campaign):
            show_warning(f"  KARMA r/{sub}: 일일 한도 도달")
            continue

        action = Action(
            action_type=ActionType.KARMA_BUILD,
            subreddit=sub, body="", is_self_promo=False,
        )
        pf = engine.pre_flight_check(action)
        if not pf.allowed:
            # 타이밍만 문제인 경우 경고만 하고 계속 진행
            timing_only = all("타이밍" in b for b in pf.blocks)
            if timing_only:
                show_warning(f"  KARMA r/{sub}: 타이밍 경고 — 계속 진행")
            else:
                show_warning(f"  KARMA r/{sub}: 차단 - {', '.join(pf.blocks)}")
                continue

        show_info(f"  KARMA r/{sub}: 포스트 탐색...")

        # HOT 포스트 읽기
        browser.browser.ext_navigate(f"https://www.reddit.com/r/{sub}/hot/")
        browser._wait_load(4)

        # 포스트 링크 수집
        links = browser.browser.ext_evaluate("""
            (() => {
                const posts = document.querySelectorAll('a[href*="/comments/"]');
                const results = [];
                const seen = new Set();
                for (const a of posts) {
                    const href = a.href;
                    if (href && href.includes('/comments/') && !seen.has(href)) {
                        seen.add(href);
                        const id = href.match(/\\/comments\\/([^/]+)/);
                        results.push({url: href, title: (a.textContent || '').substring(0, 100), id: id ? id[1] : ''});
                        if (results.length >= 8) break;
                    }
                }
                return results;
            })()
        """)

        if not links or not isinstance(links, list) or len(links) == 0:
            text = browser.browser.ext_get_text()
            show_info(f"  KARMA r/{sub}: 텍스트 기반으로 탐색 ({len(text or '')}자)")
            engine.log_executed(action)
            continue

        show_info(f"  KARMA r/{sub}: {len(links)}개 포스트 발견")

        # 중복 확인 후 타겟 선택
        commented_ids = db.get_commented_submission_ids()
        target = None
        for link in links:
            post_id = link.get("id", "")
            if post_id and post_id not in commented_ids:
                target = link
                break
        if not target:
            target = links[0]

        show_info(f"    타겟: {target.get('title', '?')[:60]}")

        # 포스트 내용 읽기
        browser.browser.ext_navigate(target["url"])
        browser._wait_load(3)

        # 사람처럼: 포스트 읽는 시간 + 스크롤
        read_time = random.uniform(5, 15)
        show_info(f"    포스트 읽는 중... ({int(read_time)}초)")
        time.sleep(read_time / 2)
        browser.browser.ext_scroll("down", random.randint(200, 600))
        time.sleep(read_time / 2)

        post_text = browser.browser.ext_get_text() or ""
        show_info(f"    포스트 내용 ({len(post_text)}자)")

        # 기존 댓글 수집 (kimi가 참조)
        existing_comments = browser.browser.reddit_get_comments(limit=10)
        if existing_comments:
            show_info(f"    기존 댓글 {len(existing_comments)}개 참조")

        # 스크롤 올려서 댓글 입력란 보이게
        browser.browser.ext_scroll("up", random.randint(300, 800))
        time.sleep(random.uniform(1, 3))

        # 댓글 생성 (기존 댓글 참조)
        from .comment_generator import generate_karma_comment
        tone = campaign.karma_tone if campaign else "helpful_expert"
        keywords = task.search_keywords or []
        comment = generate_karma_comment(post_text, sub, tone, keywords,
                                         existing_comments=existing_comments)
        show_info(f"    생성된 댓글: {comment[:80]}...")

        # 댓글 작성
        max_comments = task.max_comments or 2
        result = browser.post_comment(target["url"], comment, comment_type="karma_build")

        # kimi 기반 검증: 페이지 리로드 후 댓글 존재 확인
        from .comment_generator import verify_comment_posted
        time.sleep(3)
        browser.browser.ext_navigate(target["url"])
        browser._wait_load(4)
        verify_text = browser.browser.ext_get_text() or ""
        verification = verify_comment_posted(verify_text, comment)

        if verification["verified"]:
            show_success(f"    KARMA 댓글 검증 완료! r/{sub} ({verification['reason']})")
            db.save_browsed_post(sub, target.get("id", ""), target.get("title", ""),
                               "", target["url"])
        else:
            show_warning(f"    KARMA 댓글 미검증: {verification['reason']}")

        engine.log_executed(action)

        # 랜덤 딜레이 (봇 감지 회피)
        delay = _get_random_delay(campaign)
        show_info(f"    {int(delay)}초 대기...")
        time.sleep(delay)


def _exec_seed(browser: RedditBrowser, db: StateDB, engine: MarketingEngine,
               task: DayTask, campaign=None):
    """씨뿌리기 - 관련 포스트에 자연스러운 앱 언급."""
    for sub in task.subreddits:
        # 일일 한도 확인
        if not _check_daily_limit(db, "seeding", campaign):
            show_warning(f"  SEED r/{sub}: 일일 한도 도달")
            continue

        action = Action(
            action_type=ActionType.SEEDING,
            subreddit=sub, body="", is_self_promo=False,
        )
        pf = engine.pre_flight_check(action)
        if not pf.allowed:
            timing_only = all("타이밍" in b for b in pf.blocks)
            if timing_only:
                show_warning(f"  SEED r/{sub}: 타이밍 경고 — 계속 진행")
            else:
                show_warning(f"  SEED r/{sub}: 차단 - {', '.join(pf.blocks)}")
                continue

        show_info(f"  SEED r/{sub}: 관련 포스트 검색...")

        # 키워드 검색
        keywords = task.search_keywords or ["tool"]
        query = keywords[0] if keywords else "tool"

        browser.browser.ext_navigate(
            f"https://www.reddit.com/r/{sub}/search/?q={query}&restrict_sr=1&sort=new&t=week"
        )
        browser._wait_load(4)

        # 검색 결과 수집
        links = browser.browser.ext_evaluate("""
            (() => {
                const posts = document.querySelectorAll('a[href*="/comments/"]');
                const results = [];
                const seen = new Set();
                for (const a of posts) {
                    const href = a.href;
                    if (href && href.includes('/comments/') && !seen.has(href)) {
                        seen.add(href);
                        const id = href.match(/\\/comments\\/([^/]+)/);
                        results.push({url: href, title: (a.textContent || '').substring(0, 100), id: id ? id[1] : ''});
                        if (results.length >= 5) break;
                    }
                }
                return results;
            })()
        """)

        if not links or not isinstance(links, list) or len(links) == 0:
            text = browser.browser.ext_get_text()
            show_warning(f"  SEED r/{sub}: 포스트 미발견 - 건너뜀")
            continue

        # 중복 확인
        commented_ids = db.get_commented_submission_ids()
        target = None
        for link in links:
            post_id = link.get("id", "")
            if post_id and post_id not in commented_ids:
                target = link
                break
        if not target:
            target = links[0]

        show_info(f"  SEED r/{sub}: 타겟 '{target.get('title', '?')[:50]}'")

        # 포스트 내용 읽기
        browser.browser.ext_navigate(target["url"])
        browser._wait_load(3)

        # 사람처럼: 포스트 읽는 시간 + 스크롤
        read_time = random.uniform(5, 15)
        show_info(f"    포스트 읽는 중... ({int(read_time)}초)")
        time.sleep(read_time / 2)
        browser.browser.ext_scroll("down", random.randint(200, 600))
        time.sleep(read_time / 2)

        post_text = browser.browser.ext_get_text() or ""

        # 기존 댓글 수집 (kimi가 참조)
        existing_comments = browser.browser.reddit_get_comments(limit=10)
        if existing_comments:
            show_info(f"    기존 댓글 {len(existing_comments)}개 참조")

        browser.browser.ext_scroll("up", random.randint(300, 800))
        time.sleep(random.uniform(1, 3))

        # 씨뿌리기 댓글 생성 (기존 댓글 참조)
        if campaign:
            from .comment_generator import generate_seed_comment
            tone = campaign.seed_tone
            comment = generate_seed_comment(post_text, campaign, tone, keywords,
                                            existing_comments=existing_comments)
        else:
            comment = f"I've been exploring similar tools. Worth checking out the options available."

        show_info(f"    생성된 댓글: {comment[:80]}...")

        # 댓글 작성
        result = browser.post_comment(target["url"], comment, comment_type="seeding")

        # kimi 기반 검증
        from .comment_generator import verify_comment_posted
        time.sleep(3)
        browser.browser.ext_navigate(target["url"])
        browser._wait_load(4)
        verify_text = browser.browser.ext_get_text() or ""
        verification = verify_comment_posted(verify_text, comment)

        if verification["verified"]:
            show_success(f"    SEED 댓글 검증 완료! r/{sub} ({verification['reason']})")
            db.save_browsed_post(sub, target.get("id", ""), target.get("title", ""),
                               "", target["url"])
        else:
            show_warning(f"    SEED 댓글 미검증: {verification['reason']}")

        engine.log_executed(action)

        delay = _get_random_delay(campaign)
        show_info(f"    {int(delay)}초 대기...")
        time.sleep(delay)


def _exec_post(browser: RedditBrowser, db: StateDB, engine: MarketingEngine,
               task: DayTask, campaign=None):
    """포스트 발행 - CDP 기반."""
    sub = task.post_subreddit
    if not sub:
        return

    # 중복 포스트 방지
    if db.has_posted_to(sub, days=7):
        show_warning(f"  POST r/{sub}: 최근 7일 내 이미 포스트함 - 건너뜀")
        return

    # 일일 한도
    if db.get_today_post_count() >= (campaign.limits.posts_per_day if campaign else 1):
        show_warning(f"  POST r/{sub}: 일일 포스트 한도 도달")
        return

    action = Action(
        action_type=ActionType.POST,
        subreddit=sub,
        title=f"[준비] {task.notes}",
        body="",
        is_self_promo=True,
    )
    pf = engine.pre_flight_check(action)
    _show_preflight(pf)

    if not pf.allowed:
        show_error(f"  POST r/{sub}: 차단됨")
        for b in pf.blocks:
            show_error(f"    - {b}")
        return

    # 포스트 내용 생성
    if campaign:
        from .comment_generator import generate_post_title, generate_post_body
        title = generate_post_title(campaign, sub, task.notes)
        body = generate_post_body(campaign, sub, task.notes)
    else:
        title = task.notes or f"Sharing my project with r/{sub}"
        body = ""

    show_info(f"  POST r/{sub}: 포스트 페이지 열기...")
    show_info(f"    제목: {title}")

    # CDP 기반 포스트 발행
    result = browser.submit_post(sub, title, body)

    if result.get("status") == "ready":
        # CDP typeText로 발행
        show_info(f"  POST r/{sub}: 내용 입력 완료, 발행 시도...")
        submit_result = browser.confirm_submit()

        # URL 변경 확인 (/comments/ 포함)
        time.sleep(3)
        current_text = browser.browser.ext_get_text() or ""
        page_info = browser.browser.ext_evaluate("({url: location.href, title: document.title})")

        current_url = ""
        if isinstance(page_info, dict):
            current_url = page_info.get("url", "")

        if "/comments/" in current_url:
            show_success(f"  POST r/{sub}: 발행 성공! {current_url}")
            # DB 저장
            m = re.search(r'/comments/([^/]+)', current_url)
            reddit_id = m.group(1) if m else ""
            day_id = f"day-{task.post_subreddit}"
            db.save_submission(day_id, reddit_id, sub, title, current_url)
        else:
            show_warning(f"  POST r/{sub}: 발행 미확인 - 수동 확인 필요")
            console.print(f"    현재 URL: {current_url}")

    engine.log_executed(action)


def _exec_monitor(browser: RedditBrowser, db: StateDB, engine: MarketingEngine):
    """기존 포스트 모니터링."""
    submissions = db.get_submissions()
    if not submissions:
        show_info("  모니터링할 포스트 없음")
        return

    show_info(f"  {len(submissions)}개 포스트 모니터링")
    for sub in submissions:
        url = sub.get("url", "")
        if not url:
            continue
        stats = browser.get_post_stats(url)
        if stats:
            show_info(f"    r/{sub.get('subreddit', '?')}: "
                      f"score={stats.get('score', '?')}, "
                      f"comments={stats.get('comment_count', '?')}")
        time.sleep(2)


def _exec_review(db: StateDB, engine: MarketingEngine):
    """성과 리뷰."""
    show_info("  성과 분석...")
    console.print(engine.format_status())

    try:
        from .marketing.performance import get_subreddit_rankings, suggest_effort_reallocation
        rankings = get_subreddit_rankings(db)
        if rankings:
            show_info("  서브레딧 ROI 순위:")
            for r in rankings[:5]:
                console.print(f"    r/{r.subreddit}: ROI={r.roi_score}, "
                             f"posts={r.total_posts}, comments={r.total_comments}")
            suggestions = suggest_effort_reallocation(rankings)
            for sub_name, action_str in suggestions.items():
                console.print(f"    r/{sub_name}: {action_str}")
    except Exception:
        pass

    try:
        from .marketing.roi import fetch_github_stats, save_snapshot
        snapshot = fetch_github_stats()
        if snapshot:
            save_snapshot(db, snapshot)
            show_info(f"  GitHub: {snapshot.stars} stars, {snapshot.total_downloads} downloads")
    except Exception:
        pass


def _show_preflight(pf):
    """pre-flight 결과 표시."""
    if pf.timing:
        grade_colors = {
            "optimal": "green", "good": "green",
            "acceptable": "yellow", "poor": "yellow", "avoid": "red",
        }
        color = grade_colors.get(pf.timing.grade.value, "white")
        console.print(f"  Timing: [{color}]{pf.timing.grade.value.upper()}[/{color}] - {pf.timing.reason}")

    if pf.health:
        risk_colors = {"green": "green", "yellow": "yellow", "red": "red"}
        color = risk_colors.get(pf.health.risk_level.value, "white")
        console.print(f"  Health: [{color}]{pf.health.risk_level.value.upper()}[/{color}]")

    for w in pf.warnings:
        show_warning(f"  {w}")
    for b in pf.blocks:
        show_error(f"  BLOCK: {b}")


def _write_report(db: StateDB, engine: MarketingEngine, day_schedule: DaySchedule, campaign=None):
    """실행 보고서."""
    Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    filepath = Path(REPORT_DIR) / f"day-{day_schedule.day:02d}_{now.strftime('%Y-%m-%d_%H%M%S')}.md"

    health = engine.get_health()
    budget = engine.get_budget()

    task_summary = ", ".join(t.task_type.value for t in day_schedule.tasks)

    lines = [
        f"# Day {day_schedule.day} - {day_schedule.phase.value}",
        "",
    ]
    if campaign:
        lines.append(f"**Campaign**: {campaign.product_name}")
        lines.append(f"**URL**: {campaign.product_url}")
        lines.append("")

    lines.extend([
        f"**Phase**: {day_schedule.phase.value}",
        f"**Tasks**: {task_summary}",
        f"**Description**: {day_schedule.description}",
        "",
        "## Marketing Engine Status",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Risk Level | {health.risk_level.value} |",
        f"| Posts Today | {budget.posts_used}/{budget.posts_limit} |",
        f"| Comments Today | {budget.comments_used}/{budget.comments_limit} |",
        f"| Time | {now.strftime('%Y-%m-%d %H:%M:%S')} |",
        "",
    ])

    if health.warnings:
        lines.extend(["## Warnings", ""])
        for w in health.warnings:
            lines.append(f"- {w}")
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    show_info(f"  Report: {filepath}")


def _final_report(db: StateDB, engine: MarketingEngine):
    """최종 ROI 보고서."""
    try:
        from .marketing.roi import fetch_github_stats, save_snapshot, get_roi_summary
        show_info("GitHub 메트릭 수집...")
        snapshot = fetch_github_stats()
        if snapshot:
            save_snapshot(db, snapshot)
            show_success(f"GitHub: {snapshot.stars} stars, {snapshot.total_downloads} downloads")

        roi = get_roi_summary(db)
        show_info(f"ROI: Reddit score={roi.total_reddit_score}, "
                  f"Stars delta={roi.stars_delta}, Downloads delta={roi.downloads_delta}")
    except Exception as e:
        show_warning(f"ROI 보고서 실패: {e}")


def show_schedule(campaign_path: str | None = None):
    """30일 전체 스케줄 출력."""
    campaign = None
    if campaign_path:
        from .campaign_config import load_campaign
        campaign = load_campaign(campaign_path)
    else:
        campaign = _load_campaign_config()

    console.print(format_schedule_overview(campaign))
