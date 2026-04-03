"""날짜별 액션 오케스트레이터 + 실행 보고서 생성."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import Config
from .display import (
    confirm_action,
    show_day_plan,
    show_error,
    show_info,
    show_success,
    show_warning,
)
from .monitor import check_new_comments
from .parser import DayPlan, DayType, parse_all_days, resolve_day_id
from .reddit_client import RedditClient
from .seeding import execute_seeding
from .state import StateDB

REPORT_DIR = "data/reports"


class ExecutionReport:
    """실행 과정과 결과를 수집하여 마크다운 보고서로 출력."""

    def __init__(self, day_id: str, day_type: str, subreddit: str | None):
        self.day_id = day_id
        self.day_type = day_type
        self.subreddit = subreddit
        self.started_at = datetime.now()
        self.completed_at: datetime | None = None
        self.status = "in_progress"
        self.post_result: dict | None = None
        self.seeding_results: list[dict] = []
        self.monitor_results: list[dict] = []
        self.metrics_results: list[dict] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def set_post_result(self, reddit_id: str, url: str, title: str):
        self.post_result = {"reddit_id": reddit_id, "url": url, "title": title}

    def add_seeding_result(self, result: dict):
        self.seeding_results.append(result)

    def set_monitor_results(self, results: list[dict]):
        self.monitor_results = results

    def set_metrics_results(self, results: list[dict]):
        self.metrics_results = results

    def add_error(self, msg: str):
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def complete(self, status: str = "completed"):
        self.completed_at = datetime.now()
        self.status = status

    def write(self):
        """마크다운 보고서 파일 작성."""
        Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)
        now_str = self.started_at.strftime("%Y-%m-%d_%H%M%S")
        filepath = Path(REPORT_DIR) / f"{self.day_id}_{now_str}.md"

        duration = ""
        if self.completed_at:
            elapsed = (self.completed_at - self.started_at).total_seconds()
            duration = f"{elapsed:.0f}s"

        lines = [
            f"# Execution Report: {self.day_id}",
            "",
            "## Summary",
            "",
            f"| Item | Value |",
            f"|------|-------|",
            f"| Day | {self.day_id} |",
            f"| Type | {self.day_type} |",
            f"| Subreddit | {self.subreddit or '-'} |",
            f"| Status | {self.status} |",
            f"| Started | {self.started_at.strftime('%Y-%m-%d %H:%M:%S')} |",
            f"| Completed | {self.completed_at.strftime('%Y-%m-%d %H:%M:%S') if self.completed_at else '-'} |",
            f"| Duration | {duration} |",
            "",
        ]

        # 포스트 결과
        if self.post_result:
            lines.extend([
                "## Post",
                "",
                f"| Item | Value |",
                f"|------|-------|",
                f"| Title | {self.post_result['title'][:60]} |",
                f"| Reddit ID | {self.post_result['reddit_id']} |",
                f"| URL | {self.post_result['url']} |",
                "",
            ])

        # 씨뿌리기 결과
        if self.seeding_results:
            lines.extend([
                "## Seeding Comments",
                "",
                "| Subreddit | Status | Post Title |",
                "|-----------|--------|------------|",
            ])
            for sr in self.seeding_results:
                title = sr.get("post_title", "-")[:40]
                lines.append(f"| {sr.get('subreddit', '?')} | {sr.get('status', '?')} | {title} |")
            lines.append("")

            posted = sum(1 for s in self.seeding_results if s.get("status") == "posted")
            skipped = sum(1 for s in self.seeding_results if s.get("status") not in ("posted", "error", "dry_run"))
            errors = sum(1 for s in self.seeding_results if s.get("status") == "error")
            lines.extend([
                f"Posted: {posted} | Skipped: {skipped} | Errors: {errors}",
                "",
            ])

        # 모니터링 결과
        if self.monitor_results:
            total_new = sum(len(r.get("new_comments", [])) for r in self.monitor_results)
            lines.extend([
                "## Comment Monitoring",
                "",
                f"Total new comments found: **{total_new}**",
                "",
                "| Subreddit | Post | New Comments | Sentiments |",
                "|-----------|------|-------------|------------|",
            ])
            for mr in self.monitor_results:
                new_comments = mr.get("new_comments", [])
                sentiments = {}
                for c in new_comments:
                    s = c.get("sentiment", "neutral")
                    sentiments[s] = sentiments.get(s, 0) + 1
                sent_str = ", ".join(f"{k}:{v}" for k, v in sorted(sentiments.items()))
                lines.append(
                    f"| {mr.get('subreddit', '?')} | {mr.get('title', '?')[:30]} | "
                    f"{len(new_comments)} | {sent_str} |"
                )
            lines.append("")

            # 주요 댓글 상세
            lines.extend(["### Notable Comments", ""])
            for mr in self.monitor_results:
                for c in mr.get("new_comments", [])[:5]:
                    if c.get("priority", 0) >= 10:
                        body_short = c["body"][:100].replace("\n", " ")
                        lines.append(
                            f"- **[{mr['subreddit']}]** u/{c['author']} "
                            f"(priority:{c['priority']}, {c['sentiment']}): {body_short}"
                        )
            lines.append("")

        # 메트릭 결과
        if self.metrics_results:
            lines.extend([
                "## Metrics Snapshot",
                "",
                "| Subreddit | Upvotes | Comments |",
                "|-----------|---------|----------|",
            ])
            total_up = 0
            total_cm = 0
            for m in self.metrics_results:
                up = m.get("upvotes", 0)
                cm = m.get("comment_count", 0)
                total_up += up
                total_cm += cm
                lines.append(f"| {m.get('subreddit', '?')} | {up} | {cm} |")
            lines.append(f"| **Total** | **{total_up}** | **{total_cm}** |")
            lines.append("")

        # 에러/경고
        if self.errors:
            lines.extend(["## Errors", ""])
            for e in self.errors:
                lines.append(f"- {e}")
            lines.append("")

        if self.warnings:
            lines.extend(["## Warnings", ""])
            for w in self.warnings:
                lines.append(f"- {w}")
            lines.append("")

        # 작성
        filepath.write_text("\n".join(lines), encoding="utf-8")
        show_success(f"Report saved: {filepath}")
        return filepath


def run_day(
    config: Config,
    day_input: str,
    dry_run: bool = False,
    auto_confirm: bool = False,
):
    """특정 날짜의 캠페인 실행."""
    day_id = resolve_day_id(day_input)
    plans = parse_all_days(config.campaign.docs_dir)

    if day_id not in plans:
        show_error(f"Day '{day_id}' not found. Available: {', '.join(sorted(plans.keys()))}")
        return

    plan = plans[day_id]
    db = StateDB(config.campaign.db_path)

    # 실행 보고서 초기화
    report = ExecutionReport(day_id, plan.day_type.value, plan.subreddit)

    # 이미 완료된 날인지 확인
    status = db.get_day_status(day_id)
    if status == "completed" and not dry_run:
        show_warning(f"{day_id} is already completed.")
        if not auto_confirm and not confirm_action("Run again?"):
            db.close()
            return

    # 플레이스홀더 경고
    if plan.post and hasattr(plan.post, 'placeholders') and plan.post.placeholders:
        show_warning("Post contains unfilled placeholders:")
        for ph in plan.post.placeholders:
            show_warning(f"  → [{ph}]")
            report.add_warning(f"Unfilled placeholder: [{ph}]")
        show_warning("Edit the markdown file before posting!")

    # 미리보기
    show_day_plan(plan)

    if dry_run:
        show_info("[DRY RUN] No actual actions will be performed.")
        _dry_run_day(plan, db)
        report.complete("dry_run")
        report.write()
        db.close()
        return

    # Reddit 클라이언트 초기화
    try:
        client = RedditClient(config)
        username = client.verify_auth()
        show_success(f"Authenticated as u/{username}")
    except Exception as e:
        show_error(f"Reddit auth failed: {e}")
        show_info("Run 'python main.py setup' to configure Reddit API credentials.")
        report.add_error(f"Reddit auth failed: {e}")
        report.complete("auth_failed")
        report.write()
        db.close()
        return

    if not auto_confirm and not confirm_action(f"Execute {day_id} ({plan.day_type.value})?"):
        show_info("Cancelled.")
        report.complete("cancelled")
        report.write()
        db.close()
        return

    db.set_day_status(day_id, "in_progress")

    try:
        if plan.day_type == DayType.POST:
            _execute_post_day(client, db, plan, auto_confirm, report)
        elif plan.day_type == DayType.COMMENT_MGMT:
            _execute_comment_mgmt_day(client, db, plan, plans, auto_confirm, report)
        elif plan.day_type == DayType.PREP:
            _execute_prep_day(client, db, plan, auto_confirm, report)
        elif plan.day_type in (DayType.REST, DayType.REVIEW):
            _execute_rest_review_day(client, db, plan, plans, auto_confirm, report)

        db.set_day_status(day_id, "completed")
        report.complete("completed")
        show_success(f"\n{day_id} completed!")
    except Exception as e:
        show_error(f"Error during execution: {e}")
        db.set_day_status(day_id, "error")
        report.add_error(str(e))
        report.complete("error")
    finally:
        report.write()
        db.close()


def _dry_run_day(plan: DayPlan, db: StateDB):
    """Dry run — 파싱 결과만 보여줌."""
    show_info(f"Day type: {plan.day_type.value}")
    if plan.post:
        show_info(f"Would post to {plan.subreddit}")
    if plan.seeding_comments:
        show_info(f"Would post {len(plan.seeding_comments)} seeding comments")
    if plan.qa_pairs:
        show_info(f"Prepared {len(plan.qa_pairs)} Q&A pairs")
    if plan.previous_days_to_monitor:
        show_info(f"Would monitor: {', '.join(plan.previous_days_to_monitor)}")


def _execute_post_day(
    client: RedditClient, db: StateDB, plan: DayPlan, auto_confirm: bool,
    report: ExecutionReport,
):
    """POST 날 실행."""
    # 1. 포스트 제출
    if plan.post and plan.subreddit:
        show_info(f"\nPosting to {plan.subreddit}...")
        try:
            submission = client.submit_post(
                plan.subreddit, plan.post.title, plan.post.body
            )
            db.save_submission(
                day_id=plan.day_id,
                reddit_id=submission.id,
                subreddit=plan.subreddit,
                title=plan.post.title,
                url=f"https://reddit.com{submission.permalink}",
            )
            show_success(f"Posted! URL: https://reddit.com{submission.permalink}")
            report.set_post_result(
                submission.id,
                f"https://reddit.com{submission.permalink}",
                plan.post.title,
            )
        except Exception as e:
            show_error(f"Failed to post: {e}")
            report.add_error(f"Post failed: {e}")

    # 2. 씨뿌리기
    if plan.seeding_comments:
        show_info("\nStarting seeding comments...")
        results = execute_seeding(
            client, db, plan.seeding_comments, plan.day_id, auto_confirm=auto_confirm
        )
        for r in results:
            report.add_seeding_result(r)


def _execute_comment_mgmt_day(
    client: RedditClient,
    db: StateDB,
    plan: DayPlan,
    all_plans: dict[str, DayPlan],
    auto_confirm: bool,
    report: ExecutionReport,
):
    """COMMENT_MGMT 날 실행."""
    all_qa = list(plan.qa_pairs)
    for monitor_day in plan.previous_days_to_monitor:
        if monitor_day in all_plans and all_plans[monitor_day].qa_pairs:
            all_qa.extend(all_plans[monitor_day].qa_pairs)

    show_info("\nChecking comments on existing posts...")
    results = check_new_comments(client, db, qa_pairs=all_qa, auto_confirm=auto_confirm)
    report.set_monitor_results(results)

    # 씨뿌리기
    if plan.seeding_comments:
        show_info("\nStarting seeding comments...")
        seeding_results = execute_seeding(
            client, db, plan.seeding_comments, plan.day_id, auto_confirm=auto_confirm
        )
        for r in seeding_results:
            report.add_seeding_result(r)


def _execute_prep_day(
    client: RedditClient, db: StateDB, plan: DayPlan, auto_confirm: bool,
    report: ExecutionReport,
):
    """PREP 날 실행 — 씨뿌리기만."""
    show_info("\nPrep day — seeding comments only (no self-promotion).")
    if plan.seeding_comments:
        results = execute_seeding(
            client, db, plan.seeding_comments, plan.day_id, auto_confirm=auto_confirm
        )
        for r in results:
            report.add_seeding_result(r)
    else:
        show_info("No seeding comments defined for this prep day.")


def _execute_rest_review_day(
    client: RedditClient,
    db: StateDB,
    plan: DayPlan,
    all_plans: dict[str, DayPlan],
    auto_confirm: bool,
    report: ExecutionReport,
):
    """REST/REVIEW 날 실행."""
    show_info(f"\n{plan.day_type.value.title()} day — checking existing post comments.")

    all_qa = []
    for p in all_plans.values():
        all_qa.extend(p.qa_pairs)

    results = check_new_comments(client, db, qa_pairs=all_qa, auto_confirm=auto_confirm)
    report.set_monitor_results(results)

    if plan.day_type == DayType.REVIEW:
        show_info("\nCollecting metrics for review...")
        from .metrics import collect_metrics
        metrics = collect_metrics(client, db)
        report.set_metrics_results(metrics)
