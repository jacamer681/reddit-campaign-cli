"""Rich 터미널 UI."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from .parser import DayPlan, DayType

console = Console()


def show_day_plan(plan: DayPlan):
    """DayPlan 미리보기 출력."""
    type_colors = {
        DayType.PREP: "cyan",
        DayType.POST: "green",
        DayType.COMMENT_MGMT: "yellow",
        DayType.REST: "dim",
        DayType.REVIEW: "magenta",
    }
    color = type_colors.get(plan.day_type, "white")

    console.print()
    console.print(
        Panel(
            f"[bold]{plan.day_id}[/bold] - {plan.day_type.value.upper()}",
            style=color,
            width=60,
        )
    )

    if plan.subreddit:
        console.print(f"  Subreddit: [bold]{plan.subreddit}[/bold]")

    if plan.post:
        console.print()
        console.print(
            Panel(
                f"[bold]Title:[/bold] {plan.post.title}\n\n{plan.post.body}",
                title="Post Preview",
                border_style="green",
                width=80,
            )
        )

    if plan.qa_pairs:
        console.print()
        table = Table(title="Q&A Pairs", show_lines=True, width=80)
        table.add_column("Question", style="cyan", width=30)
        table.add_column("Answer", width=46)
        for qa in plan.qa_pairs:
            table.add_row(qa.question, qa.answer[:100] + "..." if len(qa.answer) > 100 else qa.answer)
        console.print(table)

    if plan.seeding_comments:
        console.print()
        table = Table(title="Seeding Comments", show_lines=True, width=80)
        table.add_column("Subreddit", style="yellow", width=20)
        table.add_column("Comment", width=56)
        for sc in plan.seeding_comments:
            body_preview = sc.body[:80] + "..." if len(sc.body) > 80 else sc.body
            table.add_row(sc.subreddit, body_preview or "(template)")
        console.print(table)

    if plan.previous_days_to_monitor:
        console.print()
        console.print(
            f"  Monitor: {', '.join(plan.previous_days_to_monitor)}"
        )
    console.print()


def show_status_dashboard(statuses: list[dict], submissions: list[dict]):
    """캠페인 진행 현황 대시보드."""
    console.print()
    console.print(Panel("[bold]Campaign Status Dashboard[/bold]", style="blue", width=70))

    # Status table
    table = Table(title="Day Progress", width=70)
    table.add_column("Day", style="cyan", width=12)
    table.add_column("Status", width=12)
    table.add_column("Started", width=20)
    table.add_column("Completed", width=20)

    status_icons = {
        "pending": "[dim]pending[/dim]",
        "in_progress": "[yellow]running[/yellow]",
        "completed": "[green]done[/green]",
    }

    for s in statuses:
        table.add_row(
            s["day_id"],
            status_icons.get(s["status"], s["status"]),
            (s.get("started_at") or "")[:19],
            (s.get("completed_at") or "")[:19],
        )
    console.print(table)

    # Submissions table
    if submissions:
        console.print()
        sub_table = Table(title="Submissions", width=70)
        sub_table.add_column("Day", style="cyan", width=8)
        sub_table.add_column("Subreddit", style="yellow", width=20)
        sub_table.add_column("Title", width=38)
        for s in submissions:
            sub_table.add_row(
                s["day_id"],
                s.get("subreddit", ""),
                (s.get("title") or "")[:35],
            )
        console.print(sub_table)
    console.print()


def show_metrics_report(metrics: list[dict], submissions: list[dict]):
    """메트릭 리포트 출력."""
    console.print()
    console.print(Panel("[bold]Metrics Report[/bold]", style="magenta", width=70))

    sub_map = {s["reddit_id"]: s for s in submissions if s.get("reddit_id")}

    table = Table(width=70, show_lines=True)
    table.add_column("Subreddit", style="cyan", width=20)
    table.add_column("Upvotes", justify="right", width=10)
    table.add_column("Comments", justify="right", width=10)
    table.add_column("Recorded", width=20)

    total_upvotes = 0
    total_comments = 0
    for m in metrics:
        sub = sub_map.get(m["submission_id"], {})
        upvotes = m.get("upvotes", 0)
        comments = m.get("comment_count", 0)
        total_upvotes += upvotes
        total_comments += comments
        table.add_row(
            sub.get("subreddit", m["submission_id"]),
            str(upvotes),
            str(comments),
            (m.get("recorded_at") or "")[:19],
        )

    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_upvotes}[/bold]",
        f"[bold]{total_comments}[/bold]",
        "",
    )
    console.print(table)
    console.print()


def show_monitor_results(results: list[dict]):
    """모니터링 결과 출력."""
    console.print()
    console.print(Panel("[bold]Comment Monitor[/bold]", style="yellow", width=80))

    if not results:
        console.print("  No new comments found.")
        console.print()
        return

    total_new = sum(len(r.get("new_comments", [])) for r in results)
    console.print(f"  Found [bold]{total_new}[/bold] new comments across {len(results)} posts.\n")

    for r in results:
        new_comments = r.get("new_comments", [])
        console.print(
            f"  [bold cyan]{r['subreddit']}[/bold cyan] - {r['title'][:40]} "
            f"({len(new_comments)} new)"
        )

        # 감정 분포 요약
        sentiments = {}
        for c in new_comments:
            s = c.get("sentiment", "neutral")
            sentiments[s] = sentiments.get(s, 0) + 1
        sentiment_str = " | ".join(f"{k}: {v}" for k, v in sorted(sentiments.items()))
        console.print(f"    Sentiment: {sentiment_str}")

        # 핫 토픽
        all_topics = set()
        for c in new_comments:
            all_topics.update(c.get("topics", []))
        if all_topics:
            console.print(f"    Topics: {', '.join(sorted(all_topics))}")

        console.print()

        for c in new_comments:
            author = c.get("author", "unknown")
            body = c.get("body", "")[:120].replace("\n", " ")
            priority = c.get("priority", 0)
            sentiment = c.get("sentiment", "?")

            # 우선순위 색상
            if priority >= 25:
                p_color = "red"
                p_label = "HIGH"
            elif priority >= 10:
                p_color = "yellow"
                p_label = "MED"
            else:
                p_color = "dim"
                p_label = "LOW"

            console.print(
                f"    [{p_color}][{p_label}][/{p_color}] "
                f"[yellow]{author}[/yellow] ({sentiment}): {body}"
            )
            if c.get("suggested_reply"):
                console.print(
                    f"      [green]-> Suggested:[/green] {c['suggested_reply'][:80]}..."
                )
        console.print()
    console.print()


def confirm_action(message: str) -> bool:
    """사용자 확인 프롬프트."""
    return console.input(f"\n  {message} [y/N]: ").strip().lower() in ("y", "yes")


def show_success(message: str):
    console.print(f"  [green]✓[/green] {message}")


def show_error(message: str):
    console.print(f"  [red]✗[/red] {message}")


def show_info(message: str):
    console.print(f"  [blue]ℹ[/blue] {message}")


def show_warning(message: str):
    console.print(f"  [yellow]![/yellow] {message}")
