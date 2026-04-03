"""Click CLI — 범용 Reddit 30일 마케팅 자동화 전체 터미널 컨트롤."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import click

from .config import Config, load_config
from .display import (
    console,
    show_error,
    show_info,
    show_metrics_report,
    show_monitor_results,
    show_status_dashboard,
    show_success,
    show_warning,
)


@click.group()
@click.option("--config", "config_path", default=None, help="Path to config.toml")
@click.pass_context
def cli(ctx, config_path):
    """Reddit 30-Day Campaign CLI — 터미널에서 모든 것을 관리."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


# ═══════════════════════════════════════════
# campaign 그룹 — 캠페인 설정/계획/미리보기/이력
# ═══════════════════════════════════════════

@cli.group()
def campaign():
    """캠페인 전체 관리 — init/show/plan/day/preview/history/reset."""
    pass


@campaign.command()
@click.option("--path", default="campaign.toml", help="Output path")
def init(path):
    """새 캠페인 설정 인터랙티브 생성."""
    from .campaign_config import CampaignConfig, SubTarget, PostTarget, Limits, save_campaign

    if Path(path).exists():
        show_info(f"{path} 이미 존재합니다.")
        if not click.confirm("덮어쓰시겠습니까?", default=False):
            return

    console.print("\n[bold]Campaign Setup[/bold]\n")

    name = click.prompt("  제품/프로젝트 이름", default="My Product")
    url = click.prompt("  URL (GitHub, 웹사이트 등)", default="")
    tagline = click.prompt("  한 줄 소개", default="")
    category = click.prompt("  카테고리", type=click.Choice(["developer_tool", "saas", "app", "service", "community"]),
                           default="developer_tool")
    username = click.prompt("  Reddit 사용자명", default="")

    console.print("\n  [dim]카르마 빌딩 서브레딧 (쉼표 구분)[/dim]")
    karma_str = click.prompt("  카르마 서브레딧", default="commandline,programming,webdev")
    karma_subs = [SubTarget(sub=s.strip(), keywords=[]) for s in karma_str.split(",") if s.strip()]

    console.print("\n  [dim]씨뿌리기 서브레딧 (쉼표 구분)[/dim]")
    seed_str = click.prompt("  씨뿌리기 서브레딧", default="SideProject,commandline")
    seed_subs = [SubTarget(sub=s.strip(), keywords=[]) for s in seed_str.split(",") if s.strip()]

    console.print("\n  [dim]포스팅 서브레딧 (작은 곳부터, 쉼표 구분)[/dim]")
    post_str = click.prompt("  포스팅 서브레딧", default="SideProject,commandline,programming")
    post_subs = [PostTarget(sub=s.strip()) for s in post_str.split(",") if s.strip()]

    cfg = CampaignConfig(
        product_name=name, product_url=url, tagline=tagline, category=category,
        reddit_username=username,
        karma_subs=karma_subs, seed_subs=seed_subs, post_subs=post_subs,
        karma_tone="helpful_expert", seed_tone="casual_mention",
        limits=Limits(),
    )
    save_campaign(cfg, path)
    show_success(f"캠페인 설정 저장: {path}")


@campaign.command("show")
@click.option("--path", default="campaign.toml", help="Campaign file path")
def campaign_show(path):
    """캠페인 설정 확인."""
    from .campaign_config import load_campaign
    try:
        cfg = load_campaign(path)
        console.print(f"\n  [bold]{cfg.product_name}[/bold]")
        console.print(f"  URL: {cfg.product_url}")
        console.print(f"  Tagline: {cfg.tagline}")
        console.print(f"  Category: {cfg.category}")
        console.print(f"  Reddit: u/{cfg.reddit_username}")
        console.print(f"\n  [cyan]카르마 서브레딧:[/cyan] {', '.join(s.sub for s in cfg.karma_subs)}")
        console.print(f"  [green]씨뿌리기 서브레딧:[/green] {', '.join(s.sub for s in cfg.seed_subs)}")
        console.print(f"  [yellow]포스팅 서브레딧:[/yellow] {', '.join(p.sub for p in cfg.post_subs)}")
        console.print(f"\n  카르마 톤: {cfg.karma_tone}")
        console.print(f"  씨뿌리기 톤: {cfg.seed_tone}")
        console.print(f"  일일 한도: 카르마={cfg.limits.karma_comments_per_day}, "
                      f"씨뿌리기={cfg.limits.seed_comments_per_day}, 포스트={cfg.limits.posts_per_day}")
        console.print(f"  딜레이: {cfg.limits.min_delay_seconds}-{cfg.limits.max_delay_seconds}초")
    except FileNotFoundError:
        show_error(f"{path} 없음. 'python main.py campaign init'으로 생성하세요.")


@campaign.command("plan")
def campaign_plan():
    """30일 전체 계획 상세 조회 — 날짜별 태스크/서브레딧/키워드."""
    from .campaign_config import load_campaign, campaign_exists
    from .schedule import build_schedule, build_schedule_from_config, get_effective_schedule, TaskType, Phase
    from .state import StateDB

    config = None
    if campaign_exists():
        config = load_campaign()
        console.print(f"\n  [bold]{config.product_name}[/bold] — {config.tagline}")
        console.print(f"  {config.product_url}\n")

    db = StateDB("data/campaign.db")
    schedule = get_effective_schedule(config, db)
    statuses = {s["day_id"]: s["status"] for s in db.get_all_day_statuses()}
    db.close()

    phase_colors = {
        Phase.KARMA_BUILD: "cyan",
        Phase.LIGHT_SEED: "green",
        Phase.SEED_AND_POST: "yellow",
        Phase.FULL_CAMPAIGN: "red",
    }
    phase_names = {
        Phase.KARMA_BUILD: "Phase 1: 카르마 빌딩",
        Phase.LIGHT_SEED: "Phase 2: 카르마 + 씨뿌리기",
        Phase.SEED_AND_POST: "Phase 3: 씨뿌리기 + 포스트",
        Phase.FULL_CAMPAIGN: "Phase 4: 본격 캠페인",
    }
    task_icons = {
        TaskType.KARMA_COMMENT: "[cyan]KARMA[/cyan]",
        TaskType.SEED_COMMENT: "[green]SEED[/green]",
        TaskType.POST: "[bold yellow]POST[/bold yellow]",
        TaskType.MONITOR: "[blue]MONITOR[/blue]",
        TaskType.REST: "[dim]REST[/dim]",
        TaskType.REVIEW: "[magenta]REVIEW[/magenta]",
    }
    status_icons = {"completed": "[green]OK[/green]", "in_progress": "[yellow]..[/yellow]",
                    "error": "[red]ERR[/red]", "pending": "[dim]--[/dim]"}

    current_phase = None
    for s in schedule:
        if s.phase != current_phase:
            current_phase = s.phase
            color = phase_colors.get(s.phase, "white")
            console.print(f"\n  [{color}]{'=' * 50}[/{color}]")
            console.print(f"  [{color}]{phase_names.get(s.phase, s.phase.value)}[/{color}]")
            console.print(f"  [{color}]{'=' * 50}[/{color}]")

        day_id = f"day-{s.day:02d}"
        st = statuses.get(day_id, "pending")
        st_icon = status_icons.get(st, st)

        console.print(f"\n  [bold]Day {s.day:2d}[/bold] {st_icon}  {s.description}")
        for t in s.tasks:
            icon = task_icons.get(t.task_type, t.task_type.value)
            parts = [f"    {icon}"]
            if t.subreddits:
                parts.append(f"r/{', r/'.join(t.subreddits)}")
            if t.post_subreddit:
                parts.append(f"[bold]r/{t.post_subreddit}[/bold]")
            if t.search_keywords:
                parts.append(f"[dim]({', '.join(t.search_keywords[:3])})[/dim]")
            if t.max_comments:
                parts.append(f"[dim]max={t.max_comments}[/dim]")
            if t.notes:
                parts.append(f"[dim]{t.notes}[/dim]")
            console.print(" ".join(parts))


@campaign.command("day")
@click.argument("day_num", type=int)
def campaign_day(day_num):
    """특정 날 상세 계획 + 생성될 댓글 미리보기."""
    from .campaign_config import load_campaign, campaign_exists
    from .schedule import get_effective_schedule, TaskType
    from .comment_generator import generate_karma_comment, generate_seed_comment, generate_post_title, generate_post_body
    from .state import StateDB

    config = None
    if campaign_exists():
        config = load_campaign()

    db = StateDB("data/campaign.db")
    schedule = get_effective_schedule(config, db)
    day_sched = None
    for s in schedule:
        if s.day == day_num:
            day_sched = s
            break

    if not day_sched:
        show_error(f"Day {day_num} 없음 (1-30)")
        db.close()
        return

    day_id = f"day-{day_num:02d}"
    st = db.get_day_status(day_id) or "pending"
    karma_count = db.get_today_action_count("karma_build")
    seed_count = db.get_today_action_count("seeding")
    post_count = db.get_today_post_count()
    db.close()

    status_color = {"completed": "green", "in_progress": "yellow", "error": "red"}.get(st, "dim")

    console.print(f"\n  [bold]=== Day {day_num} ===[/bold]")
    console.print(f"  Phase: {day_sched.phase.value}")
    console.print(f"  Description: {day_sched.description}")
    console.print(f"  Status: [{status_color}]{st}[/{status_color}]")
    console.print(f"  Today: karma={karma_count}, seed={seed_count}, post={post_count}")

    console.print(f"\n  [bold]Tasks ({len(day_sched.tasks)}):[/bold]")
    for i, t in enumerate(day_sched.tasks, 1):
        console.print(f"\n  [{i}] {t.task_type.value.upper()}")
        if t.subreddits:
            console.print(f"      Subreddits: {', '.join('r/' + s for s in t.subreddits)}")
        if t.post_subreddit:
            console.print(f"      Post to: r/{t.post_subreddit}")
        if t.search_keywords:
            console.print(f"      Keywords: {', '.join(t.search_keywords)}")
        if t.max_comments:
            console.print(f"      Max comments: {t.max_comments}")
        if t.notes:
            console.print(f"      Notes: {t.notes}")

        # 댓글 미리보기
        if config and t.task_type == TaskType.KARMA_COMMENT:
            for sub in t.subreddits:
                comment = generate_karma_comment(
                    "Sample post about " + " ".join(t.search_keywords[:2]),
                    sub, config.karma_tone, t.search_keywords
                )
                console.print(f"      [cyan]Preview:[/cyan] {comment}")

        elif config and t.task_type == TaskType.SEED_COMMENT:
            for sub in t.subreddits:
                comment = generate_seed_comment(
                    "Sample post about " + " ".join(t.search_keywords[:2]),
                    config, config.seed_tone, t.search_keywords
                )
                console.print(f"      [green]Preview:[/green] {comment}")

        elif config and t.task_type == TaskType.POST and t.post_subreddit:
            title = generate_post_title(config, t.post_subreddit, t.notes)
            body = generate_post_body(config, t.post_subreddit, t.notes)
            console.print(f"      [yellow]Title:[/yellow] {title}")
            console.print(f"      [yellow]Body:[/yellow] {body[:200]}...")


@campaign.command("preview")
@click.argument("day_num", type=int)
@click.option("--count", "-n", default=3, help="Number of comment variants to show")
def campaign_preview(day_num, count):
    """특정 날 댓글 변형 N개 미리보기."""
    from .campaign_config import load_campaign, campaign_exists
    from .schedule import get_effective_schedule, TaskType
    from .comment_generator import generate_karma_comment, generate_seed_comment
    from .state import StateDB

    if not campaign_exists():
        show_error("campaign.toml 없음. 'python main.py campaign init' 먼저 실행.")
        return

    config = load_campaign()
    db = StateDB("data/campaign.db")
    schedule = get_effective_schedule(config, db)
    db.close()
    day_sched = None
    for s in schedule:
        if s.day == day_num:
            day_sched = s
            break

    if not day_sched:
        show_error(f"Day {day_num} 없음")
        return

    console.print(f"\n  [bold]Day {day_num} — 댓글 미리보기 (x{count})[/bold]\n")

    for t in day_sched.tasks:
        if t.task_type == TaskType.KARMA_COMMENT:
            for sub in t.subreddits:
                console.print(f"  [cyan]KARMA r/{sub}[/cyan]")
                for i in range(count):
                    c = generate_karma_comment(
                        f"Post about {' '.join(t.search_keywords[:2])}",
                        sub, config.karma_tone, t.search_keywords
                    )
                    console.print(f"    [{i+1}] {c}")
                console.print()

        elif t.task_type == TaskType.SEED_COMMENT:
            for sub in t.subreddits:
                console.print(f"  [green]SEED r/{sub}[/green]")
                for i in range(count):
                    c = generate_seed_comment(
                        f"Post about {' '.join(t.search_keywords[:2])}",
                        config, config.seed_tone, t.search_keywords
                    )
                    console.print(f"    [{i+1}] {c}")
                console.print()


@campaign.command("history")
@click.option("--date", "-d", default=None, help="Filter by date (YYYY-MM-DD)")
@click.option("--type", "-t", "comment_type", default=None, help="Filter: karma_build, seeding, post")
@click.option("--limit", "-n", default=20, help="Max results")
def campaign_history(date, comment_type, limit):
    """활동 이력 조회 — 댓글/포스트/업보트 전체."""
    from .state import StateDB

    db = StateDB("data/campaign.db")

    # 요약
    today = date or datetime.now().strftime("%Y-%m-%d")
    summary = db.get_activity_summary(today)
    total = db.get_activity_summary()

    console.print(f"\n  [bold]=== 활동 이력 ===[/bold]")
    console.print(f"  Date: {today}\n")
    console.print(f"  Today: comments={summary['comments_total']}, posts={summary['posts_total']}, "
                  f"browsed={summary['browsed_total']}, upvotes={summary['upvotes_total']}")
    console.print(f"  Total: comments={total['comments_total']}, posts={total['posts_total']}, "
                  f"browsed={total['browsed_total']}, upvotes={total['upvotes_total']}")

    if summary.get("comments_by_type"):
        types_str = ", ".join(f"{r['comment_type']}={r['cnt']}" for r in summary["comments_by_type"])
        console.print(f"  Types: {types_str}")

    if summary.get("comments_by_sub"):
        subs_str = ", ".join(f"r/{r['subreddit']}={r['cnt']}" for r in summary["comments_by_sub"][:5])
        console.print(f"  Subs: {subs_str}")

    # 댓글 이력
    comments = db.get_comments(comment_type)
    if comments:
        console.print(f"\n  [bold]Comments ({len(comments)} total, showing last {limit}):[/bold]")
        for c in list(reversed(comments))[:limit]:
            type_color = {"karma_build": "cyan", "seeding": "green"}.get(c.get("comment_type", ""), "white")
            console.print(f"\n    [{type_color}]{c.get('comment_type', '?')}[/{type_color}] "
                          f"r/{c.get('subreddit', '?')} — {c.get('created_at', '')[:16]}")
            body = (c.get("body") or "")[:150]
            if body:
                console.print(f"    {body}")

    # 포스트 이력
    posts = db.get_submissions()
    if posts:
        console.print(f"\n  [bold]Posts ({len(posts)}):[/bold]")
        for p in posts:
            console.print(f"    r/{p.get('subreddit', '?')}: {p.get('title', '?')[:60]}")
            if p.get("url"):
                console.print(f"    [dim]{p['url']}[/dim]")

    db.close()


@campaign.command("status")
def campaign_status():
    """캠페인 진행 상태 — 30일 전체 한눈에."""
    from .state import StateDB
    from .marketing.engine import MarketingEngine

    db = StateDB("data/campaign.db")
    engine = MarketingEngine(db)

    console.print()
    console.print(engine.format_status())

    statuses = db.get_all_day_statuses()
    status_map = {s["day_id"]: s["status"] for s in statuses}

    completed = sum(1 for s in statuses if s["status"] == "completed")
    in_progress = sum(1 for s in statuses if s["status"] == "in_progress")
    errors = sum(1 for s in statuses if s["status"] == "error")

    console.print(f"\n  [bold]Progress:[/bold] {completed}/30 done, {in_progress} running, {errors} errors\n")

    # 30일 그리드
    line = "  "
    for day in range(1, 31):
        day_id = f"day-{day:02d}"
        st = status_map.get(day_id, "pending")
        if st == "completed":
            line += f"[green]{day:2d}[/green] "
        elif st == "in_progress":
            line += f"[yellow]{day:2d}[/yellow] "
        elif st == "error":
            line += f"[red]{day:2d}[/red] "
        else:
            line += f"[dim]{day:2d}[/dim] "
        if day % 10 == 0:
            console.print(line)
            line = "  "
    if line.strip():
        console.print(line)

    console.print(f"\n  [dim]green=done, yellow=running, red=error, dim=pending[/dim]")
    db.close()


@campaign.command("reset")
@click.argument("day_num", type=int)
def campaign_reset(day_num):
    """특정 날 상태를 pending으로 리셋 (재실행 가능)."""
    from .state import StateDB

    day_id = f"day-{day_num:02d}"
    db = StateDB("data/campaign.db")
    db.set_day_status(day_id, "pending")
    db.close()
    show_success(f"Day {day_num} 리셋 완료 — 재실행 가능")


@campaign.command("edit-day")
@click.argument("day_num", type=int)
@click.option("--desc", default=None, help="Day description")
@click.option("--add-karma", multiple=True, help="Add karma task: SUB:keyword1,keyword2")
@click.option("--add-seed", multiple=True, help="Add seed task: SUB:keyword1,keyword2")
@click.option("--add-post", default=None, help="Add post task: SUB")
@click.option("--add-rest", is_flag=True, help="Add rest task")
@click.option("--clear-tasks", is_flag=True, help="Clear all tasks before adding")
@click.option("--revert", is_flag=True, help="Revert to auto-generated schedule")
def campaign_edit_day(day_num, desc, add_karma, add_seed, add_post, add_rest, clear_tasks, revert):
    """특정 날의 스케줄 수정 — 태스크 추가/변경/삭제.

    Examples:
      campaign edit-day 5 --desc "카르마+씨뿌리기" --clear-tasks --add-karma commandline:terminal,cli --add-seed webdev:dev tools
      campaign edit-day 10 --add-post SideProject
      campaign edit-day 7 --revert
    """
    from .campaign_config import load_campaign, campaign_exists
    from .schedule import (
        build_schedule, build_schedule_from_config, get_effective_schedule,
        TaskType, Phase, DayTask, DaySchedule, day_schedule_to_dict
    )
    from .state import StateDB

    db = StateDB("data/campaign.db")

    # revert: DB 커스텀 삭제 → 자동 생성으로 복원
    if revert:
        db.delete_custom_schedule(day_num)
        db.close()
        show_success(f"Day {day_num} 자동 생성 스케줄로 복원됨")
        return

    # 현재 스케줄 가져오기
    config = load_campaign() if campaign_exists() else None
    schedule = get_effective_schedule(config, db)
    day_sched = None
    for s in schedule:
        if s.day == day_num:
            day_sched = s
            break

    if not day_sched:
        show_error(f"Day {day_num} 없음 (1-30)")
        db.close()
        return

    # 설명 변경
    if desc:
        day_sched.description = desc

    # 태스크 클리어
    if clear_tasks:
        day_sched.tasks = []

    # 카르마 태스크 추가
    for kt in add_karma:
        parts = kt.split(":", 1)
        sub = parts[0].strip()
        keywords = [k.strip() for k in parts[1].split(",")] if len(parts) > 1 else []
        day_sched.tasks.append(DayTask(
            task_type=TaskType.KARMA_COMMENT,
            subreddits=[sub],
            search_keywords=keywords,
            max_comments=2,
            notes=f"r/{sub}에서 도움 댓글 (앱 언급 금지)",
        ))

    # 씨뿌리기 태스크 추가
    for st_val in add_seed:
        parts = st_val.split(":", 1)
        sub = parts[0].strip()
        keywords = [k.strip() for k in parts[1].split(",")] if len(parts) > 1 else []
        day_sched.tasks.append(DayTask(
            task_type=TaskType.SEED_COMMENT,
            subreddits=[sub],
            search_keywords=keywords,
            max_comments=1,
            notes=f"씨뿌리기: r/{sub} (자연스러운 언급)",
        ))

    # 포스트 태스크 추가
    if add_post:
        day_sched.tasks.append(DayTask(
            task_type=TaskType.POST,
            post_subreddit=add_post,
            notes=f"r/{add_post}에 포스트",
        ))

    # 휴식 태스크 추가
    if add_rest:
        day_sched.tasks = [DayTask(task_type=TaskType.REST, notes="휴식")]

    # DB에 저장
    import json as _json
    tasks_json = _json.dumps([
        {"task_type": t.task_type.value, "subreddits": t.subreddits,
         "search_keywords": t.search_keywords, "max_comments": t.max_comments,
         "post_subreddit": t.post_subreddit, "notes": t.notes}
        for t in day_sched.tasks
    ], ensure_ascii=False)
    db.save_custom_schedule(day_num, day_sched.phase.value, day_sched.description, tasks_json)
    db.close()

    show_success(f"Day {day_num} 스케줄 저장 완료")
    console.print(f"  Description: {day_sched.description}")
    console.print(f"  Tasks: {len(day_sched.tasks)}개")
    for i, t in enumerate(day_sched.tasks, 1):
        parts = [f"    [{i}] {t.task_type.value.upper()}"]
        if t.subreddits:
            parts.append(f"r/{', r/'.join(t.subreddits)}")
        if t.post_subreddit:
            parts.append(f"r/{t.post_subreddit}")
        if t.search_keywords:
            parts.append(f"({', '.join(t.search_keywords[:3])})")
        console.print(" ".join(parts))


cli.add_command(campaign)


# ═══════════════════════════════════════════
# browser — 레딧브라우저 자동화 실행
# ═══════════════════════════════════════════

@cli.command()
@click.option("--all", "run_all", is_flag=True, help="Run all remaining days")
@click.option("--schedule", "show_schedule", is_flag=True, help="Show 30-day schedule")
@click.option("--status", "show_status", is_flag=True, help="Show progress")
@click.option("--dry-run", is_flag=True, help="Preview without posting")
@click.option("--delay", default=30, help="Delay between days (seconds)")
@click.option("--day", "start_day", default=None, type=int, help="Start from specific day")
@click.option("--campaign", "campaign_path", default=None, help="Path to campaign.toml")
@click.pass_context
def browser(ctx, run_all, show_schedule, show_status, dry_run, delay, start_day, campaign_path):
    """레딧브라우저로 전자동 실행 — API 키 불필요."""
    if show_schedule:
        from .autopilot_browser import show_schedule as _show
        _show(campaign_path)
        return

    if show_status:
        from .state import StateDB
        db = StateDB("data/campaign.db")
        from .marketing.engine import MarketingEngine
        engine = MarketingEngine(db)
        console.print(engine.format_status())
        statuses = db.get_all_day_statuses()
        if statuses:
            console.print("\n  진행 현황:")
            for s in statuses:
                icon = {"completed": "[green]OK[/green]", "in_progress": "[yellow]...[/yellow]",
                        "error": "[red]ERR[/red]"}.get(s["status"], s["status"])
                console.print(f"    {s['day_id']}: {icon}")
        db.close()
        return

    from .autopilot_browser import run_browser_campaign
    run_browser_campaign(
        db_path="data/campaign.db",
        run_all=run_all,
        dry_run=dry_run,
        delay=delay,
        start_day=start_day,
        campaign_path=campaign_path,
    )


# ═══════════════════════════════════════════
# 기존 명령어들
# ═══════════════════════════════════════════

@cli.command()
@click.option("--date", "date_str", default=None, help="Date (YYYY-MM-DD)")
@click.pass_context
def summary(ctx, date_str):
    """모니터링 로그에서 일별 종합 요약."""
    from .monitor import generate_daily_summary
    generate_daily_summary(date_str=date_str)


@cli.command()
@click.option("--user", "-u", default=None, help="Reddit username")
@click.option("--url", default=None, help="Reddit post permalink")
@click.pass_context
def influence(ctx, user, url):
    """Reddit 영향력 분석."""
    from .influence import fetch_influence_data, show_influence_summary, write_influence_report
    from .state import StateDB
    cfg = load_config(ctx.obj.get("config_path"))
    db = StateDB(cfg.campaign.db_path)
    show_info("Fetching Reddit data...")
    results = fetch_influence_data(db, username=user, permalink=url)
    if results:
        show_influence_summary(results)
        report_path = write_influence_report(results)
        show_success(f"Report saved: {report_path}")
    else:
        show_error("No data collected.")
    db.close()


@cli.command()
@click.option("--date", "-d", default=None, help="Date filter (YYYY-MM-DD)")
@click.pass_context
def dashboard(ctx, date):
    """Reddit 활동 대시보드."""
    from .dashboard import show_dashboard
    show_dashboard(date=date)


@cli.command()
@click.option("--karma", "-k", default=0, type=int, help="Current karma")
def report(karma):
    """매일 전략 리포트 생성."""
    from .state import StateDB
    from .strategy_advisor import format_strategy_report, generate_daily_report, suggest_next_day_strategy

    db = StateDB("data/campaign.db")
    show_info("Generating daily report...")
    report_data = generate_daily_report(db, karma=karma)

    console.print()
    console.print(f"  Date: {report_data['date']}")
    console.print(f"  Karma: {report_data['karma']} ({'+' if report_data['karma_change'] >= 0 else ''}{report_data['karma_change']})")
    console.print(f"  Comments: {report_data['comments']} | Posts: {report_data['posts']} | Upvotes: {report_data['upvotes']}")
    console.print(f"  Risk: {report_data['risk_level']}")

    console.print()
    strategies = suggest_next_day_strategy(db)
    console.print(format_strategy_report(strategies))

    db.close()
    show_success("Daily report saved.")


@cli.command()
@click.option("--port", "-p", default=8090, help="Server port")
@click.option("--host", default="0.0.0.0", help="Server host")
def web(port, host):
    """웹 대시보드 서버."""
    from .web_dashboard import run_web_dashboard
    show_info(f"Starting web dashboard on http://localhost:{port}")
    run_web_dashboard(port=port)


