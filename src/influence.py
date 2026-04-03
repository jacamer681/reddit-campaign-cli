"""Reddit 영향력 분석 — redd 라이브러리로 포스트/댓글 데이터 수집 + 보고서."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from redd import Redd, Category, TimeFilter

from .display import console, show_error, show_info, show_success, show_warning
from .state import StateDB

REPORT_DIR = "data/influence-reports"


def _flatten_comments(comments, depth=0) -> list[dict]:
    """댓글 트리를 플랫 리스트로 변환."""
    flat = []
    for c in comments:
        flat.append({
            "author": c.author,
            "body": c.body,
            "score": c.score,
            "depth": depth,
        })
        if c.replies:
            flat.extend(_flatten_comments(c.replies, depth + 1))
    return flat


def _sentiment_label(body: str) -> str:
    """간단한 감정 분류."""
    body_lower = body.lower()
    positive = ["awesome", "cool", "great", "love", "nice", "amazing", "solid", "impressive", "thank"]
    negative = ["bad", "suck", "hate", "terrible", "ugly", "useless", "bloat", "garbage", "waste"]
    question = ["?", "how do", "does it", "can it", "is there", "what about", "any plan"]

    pos_count = sum(1 for w in positive if w in body_lower)
    neg_count = sum(1 for w in negative if w in body_lower)

    if any(q in body_lower for q in question):
        return "question"
    if neg_count > pos_count:
        return "negative"
    if pos_count > 0:
        return "positive"
    return "neutral"


def fetch_influence_data(
    db: StateDB,
    username: str | None = None,
    permalink: str | None = None,
) -> list[dict]:
    """DB에 저장된 submission들 또는 직접 permalink로 Reddit 데이터 수집."""
    results = []

    with Redd(throttle=(1.0, 3.0)) as r:
        # 1) permalink 직접 지정
        if permalink:
            show_info(f"Fetching: {permalink}")
            try:
                detail = r.get_post(permalink)
                results.append(_process_post_detail(detail))
            except Exception as e:
                show_error(f"Failed to fetch {permalink}: {e}")
            return results

        # 2) username으로 유저 포스트 조회
        if username:
            show_info(f"Fetching posts by u/{username}...")
            try:
                posts = r.get_user_posts(username, limit=50, category=Category.NEW)
                show_info(f"Found {len(posts)} posts by u/{username}")
                for post in posts:
                    try:
                        detail = r.get_post(post.permalink)
                        results.append(_process_post_detail(detail))
                    except Exception as e:
                        show_warning(f"Skipped {post.permalink}: {e}")
            except Exception as e:
                show_error(f"Failed to fetch user posts: {e}")
            return results

        # 3) DB submissions에서 URL 가져오기
        submissions = db.get_submissions()
        if not submissions:
            show_warning("No submissions in DB. Use --user or --url option.")
            return results

        for sub in submissions:
            url = sub.get("url", "")
            if not url:
                continue
            # URL에서 permalink 추출
            plink = url.replace("https://reddit.com", "").replace("https://www.reddit.com", "")
            show_info(f"Fetching: r/{sub.get('subreddit', '?')} - {sub.get('title', '?')[:40]}")
            try:
                detail = r.get_post(plink)
                results.append(_process_post_detail(detail, day_id=sub.get("day_id")))
            except Exception as e:
                show_warning(f"Skipped: {e}")

    return results


def _process_post_detail(detail, day_id: str | None = None) -> dict:
    """PostDetail → 분석 dict로 변환."""
    comments = _flatten_comments(detail.comments)

    # 감정 분류
    sentiments = {"positive": 0, "negative": 0, "neutral": 0, "question": 0}
    for c in comments:
        s = _sentiment_label(c["body"])
        c["sentiment"] = s
        sentiments[s] = sentiments.get(s, 0) + 1

    # 상위 댓글 (score 기준)
    top_comments = sorted(comments, key=lambda x: x["score"], reverse=True)[:10]

    # 부정적 댓글
    negative_comments = [c for c in comments if c["sentiment"] == "negative"]
    negative_comments.sort(key=lambda x: x["score"], reverse=True)

    # 질문 댓글
    question_comments = [c for c in comments if c["sentiment"] == "question"]

    # 유니크 참여자
    authors = {c["author"] for c in comments if c["author"] not in ("[deleted]", "AutoModerator")}

    # 평균 score
    avg_score = sum(c["score"] for c in comments) / len(comments) if comments else 0

    return {
        "day_id": day_id,
        "title": detail.title,
        "author": detail.author,
        "subreddit": detail.subreddit,
        "url": detail.url,
        "score": detail.score,
        "num_comments": detail.num_comments,
        "created_utc": detail.created_utc,
        "comments_fetched": len(comments),
        "sentiments": sentiments,
        "top_comments": top_comments,
        "negative_comments": negative_comments[:5],
        "question_comments": question_comments[:10],
        "unique_authors": len(authors),
        "avg_comment_score": round(avg_score, 1),
        "max_comment_depth": max((c["depth"] for c in comments), default=0),
    }


def write_influence_report(results: list[dict]) -> Path:
    """영향력 분석 보고서 마크다운 작성."""
    Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    filepath = Path(REPORT_DIR) / f"influence_{now.strftime('%Y-%m-%d_%H%M%S')}.md"

    lines = [
        "# Reddit Influence Report",
        "",
        f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    if not results:
        lines.append("No data collected.")
        filepath.write_text("\n".join(lines), encoding="utf-8")
        return filepath

    # 전체 요약
    total_score = sum(r["score"] for r in results)
    total_comments = sum(r["num_comments"] for r in results)
    total_authors = sum(r["unique_authors"] for r in results)
    all_sentiments = {"positive": 0, "negative": 0, "neutral": 0, "question": 0}
    for r in results:
        for k, v in r["sentiments"].items():
            all_sentiments[k] = all_sentiments.get(k, 0) + v

    lines.extend([
        "## Overall Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Posts Analyzed | {len(results)} |",
        f"| Total Upvotes | {total_score} |",
        f"| Total Comments | {total_comments} |",
        f"| Unique Participants | {total_authors} |",
        f"| Positive Sentiment | {all_sentiments['positive']} ({_pct(all_sentiments['positive'], total_comments)}) |",
        f"| Negative Sentiment | {all_sentiments['negative']} ({_pct(all_sentiments['negative'], total_comments)}) |",
        f"| Questions | {all_sentiments['question']} ({_pct(all_sentiments['question'], total_comments)}) |",
        f"| Neutral | {all_sentiments['neutral']} ({_pct(all_sentiments['neutral'], total_comments)}) |",
        "",
    ])

    # 포스트별 비교
    lines.extend([
        "## Post Performance Comparison",
        "",
        "| # | Subreddit | Title | Score | Comments | Authors | Pos | Neg | Q |",
        "|---|-----------|-------|-------|----------|---------|-----|-----|---|",
    ])
    for i, r in enumerate(sorted(results, key=lambda x: x["score"], reverse=True), 1):
        s = r["sentiments"]
        lines.append(
            f"| {i} | r/{r['subreddit']} | {r['title'][:35]} | "
            f"{r['score']} | {r['num_comments']} | {r['unique_authors']} | "
            f"{s['positive']} | {s['negative']} | {s['question']} |"
        )
    lines.append("")

    # 각 포스트 상세
    for r in results:
        lines.extend([
            f"---",
            "",
            f"## {'[' + r['day_id'] + '] ' if r['day_id'] else ''}r/{r['subreddit']}: {r['title'][:60]}",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Score | {r['score']} |",
            f"| Comments (total) | {r['num_comments']} |",
            f"| Comments (fetched) | {r['comments_fetched']} |",
            f"| Unique Authors | {r['unique_authors']} |",
            f"| Avg Comment Score | {r['avg_comment_score']} |",
            f"| Max Thread Depth | {r['max_comment_depth']} |",
            "",
        ])

        # 감정 분포
        s = r["sentiments"]
        total = sum(s.values()) or 1
        lines.extend([
            "### Sentiment Distribution",
            "",
            f"- Positive: {s['positive']} ({_pct(s['positive'], total)})",
            f"- Negative: {s['negative']} ({_pct(s['negative'], total)})",
            f"- Question: {s['question']} ({_pct(s['question'], total)})",
            f"- Neutral: {s['neutral']} ({_pct(s['neutral'], total)})",
            "",
        ])

        # Top 댓글
        if r["top_comments"]:
            lines.extend(["### Top Comments (by score)", ""])
            for c in r["top_comments"][:5]:
                body = c["body"][:150].replace("\n", " ")
                lines.append(
                    f"- **u/{c['author']}** (score: {c['score']}, {c['sentiment']}): {body}"
                )
            lines.append("")

        # 부정 댓글
        if r["negative_comments"]:
            lines.extend(["### Negative Comments", ""])
            for c in r["negative_comments"]:
                body = c["body"][:150].replace("\n", " ")
                lines.append(
                    f"- **u/{c['author']}** (score: {c['score']}): {body}"
                )
            lines.append("")

        # 질문 댓글
        if r["question_comments"]:
            lines.extend(["### Questions Asked", ""])
            for c in r["question_comments"][:5]:
                body = c["body"][:150].replace("\n", " ")
                lines.append(f"- **u/{c['author']}**: {body}")
            lines.append("")

    # 인사이트
    lines.extend([
        "---",
        "",
        "## Key Insights",
        "",
    ])

    best = max(results, key=lambda x: x["score"])
    worst = min(results, key=lambda x: x["score"])
    most_engaged = max(results, key=lambda x: x["unique_authors"])
    most_negative = max(results, key=lambda x: x["sentiments"]["negative"])

    lines.extend([
        f"- **Best performing post**: r/{best['subreddit']} (score: {best['score']})",
        f"- **Most engaged post**: r/{most_engaged['subreddit']} ({most_engaged['unique_authors']} unique authors)",
        f"- **Most negative reception**: r/{most_negative['subreddit']} ({most_negative['sentiments']['negative']} negative comments)",
    ])

    if len(results) > 1:
        lines.append(f"- **Lowest performing**: r/{worst['subreddit']} (score: {worst['score']})")

    neg_rate = all_sentiments["negative"] / total_comments * 100 if total_comments else 0
    if neg_rate > 20:
        lines.append(f"- **Warning**: High negative sentiment rate ({neg_rate:.0f}%) — review messaging strategy")
    elif neg_rate < 5:
        lines.append(f"- **Good**: Low negative sentiment ({neg_rate:.0f}%) — messaging is well received")

    q_rate = all_sentiments["question"] / total_comments * 100 if total_comments else 0
    if q_rate > 30:
        lines.append(f"- **Note**: High question rate ({q_rate:.0f}%) — consider adding FAQ to posts")

    lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


def show_influence_summary(results: list[dict]):
    """터미널에 영향력 요약 출력."""
    from rich.panel import Panel
    from rich.table import Table

    console.print()
    console.print(Panel("[bold]Reddit Influence Analysis[/bold]", style="magenta", width=80))

    if not results:
        console.print("  No data collected.")
        return

    # 요약 테이블
    table = Table(width=80, show_lines=True)
    table.add_column("Subreddit", style="cyan", width=18)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Comments", justify="right", width=10)
    table.add_column("Authors", justify="right", width=9)
    table.add_column("Pos", justify="right", style="green", width=6)
    table.add_column("Neg", justify="right", style="red", width=6)
    table.add_column("Q", justify="right", style="yellow", width=6)

    total_score = 0
    total_comments = 0
    total_authors = 0

    for r in sorted(results, key=lambda x: x["score"], reverse=True):
        s = r["sentiments"]
        total_score += r["score"]
        total_comments += r["num_comments"]
        total_authors += r["unique_authors"]
        table.add_row(
            f"r/{r['subreddit']}",
            str(r["score"]),
            str(r["num_comments"]),
            str(r["unique_authors"]),
            str(s["positive"]),
            str(s["negative"]),
            str(s["question"]),
        )

    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_score}[/bold]",
        f"[bold]{total_comments}[/bold]",
        f"[bold]{total_authors}[/bold]",
        "", "", "",
    )
    console.print(table)

    # Top 3 댓글
    all_comments = []
    for r in results:
        for c in r["top_comments"][:3]:
            c["_sub"] = r["subreddit"]
            all_comments.append(c)
    all_comments.sort(key=lambda x: x["score"], reverse=True)

    if all_comments:
        console.print()
        console.print("[bold]Top Comments:[/bold]")
        for c in all_comments[:5]:
            body = c["body"][:100].replace("\n", " ")
            console.print(
                f"  [cyan]r/{c['_sub']}[/cyan] u/{c['author']} "
                f"(score:{c['score']}): {body}"
            )

    console.print()


def _pct(part: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{part / total * 100:.0f}%"
