"""Reddit 활동 대시보드 — 모든 활동 내역 조회."""

from __future__ import annotations

from datetime import datetime, timedelta

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .state import StateDB

console = Console()


def show_dashboard(db_path: str = "data/campaign.db", date: str | None = None):
    """전체 활동 대시보드."""
    db = StateDB(db_path)
    today = date or datetime.now().strftime("%Y-%m-%d")

    summary = db.get_activity_summary(today)
    all_summary = db.get_activity_summary()

    # ═══ Header ═══
    console.print()
    console.print(Panel(
        f"[bold]Reddit Campaign Dashboard[/bold]\n"
        f"Date: {today}  |  All Time Stats Below",
        style="blue", width=78,
    ))

    # ═══ Today Summary ═══
    today_table = Table(title=f"Today ({today})", width=78, show_lines=True)
    today_table.add_column("Metric", style="cyan", width=25)
    today_table.add_column("Today", justify="right", width=12)
    today_table.add_column("All Time", justify="right", width=12)

    today_table.add_row("Comments", str(summary["comments_total"]), str(all_summary["comments_total"]))
    today_table.add_row("Posts", str(summary["posts_total"]), str(all_summary["posts_total"]))
    today_table.add_row("Browsed Posts", str(summary["browsed_total"]), str(all_summary["browsed_total"]))
    today_table.add_row("Upvotes Given", str(summary["upvotes_total"]), str(all_summary["upvotes_total"]))
    console.print(today_table)

    # ═══ Comments by Type ═══
    if all_summary["comments_by_type"]:
        type_table = Table(title="Comments by Type", width=78)
        type_table.add_column("Type", style="yellow", width=20)
        type_table.add_column("Count", justify="right", width=10)
        type_icons = {
            "karma_build": "karma_build (no promo)",
            "seeding": "seeding (subtle mention)",
            "auto_reply": "auto_reply",
            "reply": "reply",
        }
        for row in all_summary["comments_by_type"]:
            label = type_icons.get(row["comment_type"], row["comment_type"] or "unknown")
            type_table.add_row(label, str(row["cnt"]))
        console.print(type_table)

    # ═══ Comments by Subreddit ═══
    if all_summary["comments_by_sub"]:
        sub_table = Table(title="Comments by Subreddit", width=78)
        sub_table.add_column("Subreddit", style="green", width=25)
        sub_table.add_column("Count", justify="right", width=10)
        for row in all_summary["comments_by_sub"]:
            sub_table.add_row(f"r/{row['subreddit']}", str(row["cnt"]))
        console.print(sub_table)

    # ═══ Recent Comments ═══
    _show_recent_comments(db)

    # ═══ Recent Posts ═══
    _show_recent_posts(db)

    # ═══ Recent Browsed ═══
    _show_recent_browsed(db)

    # ═══ Recent Upvotes ═══
    _show_recent_upvotes(db)

    # ═══ Campaign Progress ═══
    _show_campaign_progress(db)

    db.close()


def _show_recent_comments(db: StateDB, limit: int = 20):
    """최근 댓글 내역."""
    comments = db.get_comments()
    if not comments:
        return

    console.print()
    table = Table(title=f"Recent Comments ({len(comments)} total)", width=78, show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Time", style="dim", width=16)
    table.add_column("Type", style="yellow", width=12)
    table.add_column("Subreddit", style="green", width=14)
    table.add_column("Comment", width=29)

    for i, c in enumerate(reversed(comments[-limit:])):
        time_str = (c.get("created_at") or "")[:16].replace("T", " ")
        body = (c.get("body") or "")[:60].replace("\n", " ")
        table.add_row(
            str(len(comments) - i),
            time_str,
            c.get("comment_type", "?"),
            f"r/{c.get('subreddit', '?')}",
            body,
        )
    console.print(table)


def _show_recent_posts(db: StateDB):
    """최근 포스트 내역."""
    submissions = db.get_submissions()
    if not submissions:
        return

    console.print()
    table = Table(title=f"Posts ({len(submissions)} total)", width=78, show_lines=True)
    table.add_column("Time", style="dim", width=16)
    table.add_column("Subreddit", style="green", width=16)
    table.add_column("Title", width=36)
    table.add_column("URL", style="dim", width=6)

    for s in reversed(submissions[-10:]):
        time_str = (s.get("posted_at") or "")[:16].replace("T", " ")
        url_short = "link" if s.get("url") else "-"
        table.add_row(
            time_str,
            f"r/{s.get('subreddit', '?')}",
            (s.get("title") or "")[:34],
            url_short,
        )
    console.print(table)


def _show_recent_browsed(db: StateDB, limit: int = 15):
    """최근 읽은 포스트."""
    browsed = db.get_browsed_posts()
    if not browsed:
        return

    console.print()
    table = Table(title=f"Browsed Posts ({len(browsed)} total)", width=78)
    table.add_column("Time", style="dim", width=16)
    table.add_column("Subreddit", style="green", width=14)
    table.add_column("Title", width=32)
    table.add_column("Score", justify="right", width=6)
    table.add_column("Cmts", justify="right", width=5)

    for b in browsed[:limit]:
        time_str = (b.get("browsed_at") or "")[:16].replace("T", " ")
        table.add_row(
            time_str,
            f"r/{b.get('subreddit', '?')}",
            (b.get("title") or "")[:30],
            str(b.get("score", 0)),
            str(b.get("comment_count", 0)),
        )
    console.print(table)


def _show_recent_upvotes(db: StateDB, limit: int = 15):
    """최근 좋아요."""
    upvotes = db.get_upvotes()
    if not upvotes:
        return

    console.print()
    table = Table(title=f"Upvotes Given ({len(upvotes)} total)", width=78)
    table.add_column("Time", style="dim", width=16)
    table.add_column("Type", style="yellow", width=8)
    table.add_column("Subreddit", style="green", width=14)
    table.add_column("Title", width=36)

    for u in upvotes[:limit]:
        time_str = (u.get("created_at") or "")[:16].replace("T", " ")
        table.add_row(
            time_str,
            u.get("target_type", "?"),
            f"r/{u.get('subreddit', '?')}",
            (u.get("title") or "")[:34],
        )
    console.print(table)


def _show_campaign_progress(db: StateDB):
    """캠페인 진행 현황."""
    statuses = db.get_all_day_statuses()
    if not statuses:
        return

    console.print()
    completed = sum(1 for s in statuses if s["status"] == "completed")
    total = 33  # prep-d3 ~ day-30

    # Progress bar
    bar_width = 40
    filled = int(bar_width * completed / total) if total > 0 else 0
    bar = "[green]" + "█" * filled + "[/green]" + "[dim]░[/dim]" * (bar_width - filled)

    console.print(Panel(
        f"Campaign Progress: {completed}/{total} days\n"
        f"[{bar}] {completed * 100 // total}%",
        title="Campaign",
        width=78,
    ))

    # Day status grid
    status_icons = {
        "completed": "[green]●[/green]",
        "in_progress": "[yellow]◐[/yellow]",
        "error": "[red]✗[/red]",
        "pending": "[dim]○[/dim]",
    }

    status_map = {s["day_id"]: s["status"] for s in statuses}
    line = "  "
    days = [f"prep-d{i}" for i in range(3, 0, -1)] + [f"day-{i:02d}" for i in range(1, 31)]
    for i, day_id in enumerate(days):
        status = status_map.get(day_id, "pending")
        icon = status_icons.get(status, "[dim]?[/dim]")
        line += icon + " "
        if (i + 1) % 11 == 0:
            console.print(line)
            line = "  "
    if line.strip():
        console.print(line)

    console.print()
