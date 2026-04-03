"""메트릭 수집/리포트."""

from __future__ import annotations

from .display import show_info, show_success, show_warning
from .reddit_client import RedditClient
from .state import StateDB


def collect_metrics(client: RedditClient, db: StateDB) -> list[dict]:
    """모든 submission의 최신 메트릭 수집."""
    submissions = db.get_submissions()
    collected = []

    for sub in submissions:
        reddit_id = sub.get("reddit_id")
        if not reddit_id:
            continue

        try:
            m = client.get_submission_metrics(reddit_id)
            db.save_metrics(reddit_id, m["upvotes"], m["comment_count"])
            collected.append({
                "submission_id": reddit_id,
                "subreddit": sub.get("subreddit", ""),
                "title": sub.get("title", ""),
                **m,
            })
            show_success(
                f"  {sub.get('subreddit', '?')}: "
                f"{m['upvotes']} upvotes, {m['comment_count']} comments"
            )
        except Exception as e:
            show_warning(f"  Error collecting metrics for {reddit_id}: {e}")

    return collected
