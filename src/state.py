"""SQLite 상태 관리."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


class StateDB:
    def __init__(self, db_path: str = "data/campaign.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS campaign_state (
                day_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'pending',
                started_at TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_id TEXT NOT NULL,
                reddit_id TEXT,
                subreddit TEXT,
                title TEXT,
                url TEXT,
                posted_at TEXT
            );

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reddit_id TEXT,
                submission_id TEXT,
                subreddit TEXT,
                body TEXT,
                comment_type TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id TEXT,
                upvotes INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                recorded_at TEXT
            );

            CREATE TABLE IF NOT EXISTS comment_checks (
                submission_id TEXT PRIMARY KEY,
                last_checked_at TEXT
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT,
                subreddit TEXT,
                body_hash TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS github_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stars INTEGER DEFAULT 0,
                forks INTEGER DEFAULT 0,
                watchers INTEGER DEFAULT 0,
                total_downloads INTEGER DEFAULT 0,
                recorded_at TEXT
            );

            CREATE TABLE IF NOT EXISTS browsed_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subreddit TEXT,
                post_id TEXT,
                title TEXT,
                author TEXT,
                url TEXT,
                score INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                browsed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS upvotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT,
                target_id TEXT,
                subreddit TEXT,
                title TEXT,
                url TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT NOT NULL UNIQUE,
                karma INTEGER DEFAULT 0,
                karma_change INTEGER DEFAULT 0,
                comments_count INTEGER DEFAULT 0,
                posts_count INTEGER DEFAULT 0,
                upvotes_count INTEGER DEFAULT 0,
                browsed_count INTEGER DEFAULT 0,
                top_subreddit TEXT,
                risk_level TEXT DEFAULT 'green',
                strategy_notes TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS karma_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                karma INTEGER NOT NULL,
                recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_type TEXT,
                subreddit TEXT,
                recommendation TEXT,
                reason TEXT,
                priority INTEGER DEFAULT 0,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS custom_schedule (
                day INTEGER PRIMARY KEY,
                phase TEXT,
                description TEXT,
                tasks_json TEXT,
                updated_at TEXT
            );
        """)
        self.conn.commit()

    # --- campaign_state ---

    def get_day_status(self, day_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM campaign_state WHERE day_id = ?", (day_id,)
        ).fetchone()
        return row["status"] if row else None

    def set_day_status(self, day_id: str, status: str):
        now = datetime.now().isoformat()
        ts_field = "completed_at" if status == "completed" else "started_at"
        self.conn.execute(
            f"""INSERT INTO campaign_state (day_id, status, {ts_field})
                VALUES (?, ?, ?)
                ON CONFLICT(day_id) DO UPDATE SET status = ?, {ts_field} = ?""",
            (day_id, status, now, status, now),
        )
        self.conn.commit()

    def get_all_day_statuses(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT day_id, status, started_at, completed_at FROM campaign_state ORDER BY day_id"
        ).fetchall()
        return [dict(r) for r in rows]

    # --- submissions ---

    def save_submission(
        self, day_id: str, reddit_id: str, subreddit: str, title: str, url: str
    ):
        self.conn.execute(
            """INSERT INTO submissions (day_id, reddit_id, subreddit, title, url, posted_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (day_id, reddit_id, subreddit, title, url, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_submissions(self, day_id: str | None = None) -> list[dict]:
        if day_id:
            rows = self.conn.execute(
                "SELECT * FROM submissions WHERE day_id = ?", (day_id,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM submissions").fetchall()
        return [dict(r) for r in rows]

    def get_all_submission_reddit_ids(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT reddit_id FROM submissions WHERE reddit_id IS NOT NULL"
        ).fetchall()
        return [r["reddit_id"] for r in rows]

    # --- comments ---

    def save_comment(
        self,
        reddit_id: str,
        submission_id: str | None,
        subreddit: str,
        body: str,
        comment_type: str,
    ):
        self.conn.execute(
            """INSERT INTO comments (reddit_id, submission_id, subreddit, body, comment_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (reddit_id, submission_id, subreddit, body, comment_type, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_comments(self, comment_type: str | None = None) -> list[dict]:
        if comment_type:
            rows = self.conn.execute(
                "SELECT * FROM comments WHERE comment_type = ?", (comment_type,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM comments").fetchall()
        return [dict(r) for r in rows]

    def get_replied_comment_ids(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT reddit_id FROM comments WHERE comment_type = 'auto_reply'"
        ).fetchall()
        return {r["reddit_id"] for r in rows}

    # --- metrics ---

    def save_metrics(self, submission_id: str, upvotes: int, comment_count: int):
        self.conn.execute(
            """INSERT INTO metrics (submission_id, upvotes, comment_count, recorded_at)
               VALUES (?, ?, ?, ?)""",
            (submission_id, upvotes, comment_count, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_latest_metrics(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT m.* FROM metrics m
               INNER JOIN (
                   SELECT submission_id, MAX(recorded_at) as max_at
                   FROM metrics GROUP BY submission_id
               ) latest ON m.submission_id = latest.submission_id
               AND m.recorded_at = latest.max_at"""
        ).fetchall()
        return [dict(r) for r in rows]

    # --- comment_checks ---

    def update_comment_check(self, submission_id: str):
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT INTO comment_checks (submission_id, last_checked_at)
               VALUES (?, ?)
               ON CONFLICT(submission_id) DO UPDATE SET last_checked_at = ?""",
            (submission_id, now, now),
        )
        self.conn.commit()

    # --- browsed_posts ---

    def save_browsed_post(self, subreddit: str, post_id: str, title: str,
                          author: str, url: str, score: int = 0, comment_count: int = 0):
        self.conn.execute(
            """INSERT INTO browsed_posts (subreddit, post_id, title, author, url, score, comment_count, browsed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (subreddit, post_id, title, author, url, score, comment_count, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_browsed_posts(self, date: str | None = None) -> list[dict]:
        if date:
            rows = self.conn.execute(
                "SELECT * FROM browsed_posts WHERE browsed_at LIKE ? ORDER BY browsed_at DESC",
                (f"{date}%",)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM browsed_posts ORDER BY browsed_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # --- upvotes ---

    def save_upvote(self, target_type: str, target_id: str, subreddit: str,
                    title: str = "", url: str = ""):
        self.conn.execute(
            """INSERT INTO upvotes (target_type, target_id, subreddit, title, url, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (target_type, target_id, subreddit, title, url, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_upvotes(self, date: str | None = None) -> list[dict]:
        if date:
            rows = self.conn.execute(
                "SELECT * FROM upvotes WHERE created_at LIKE ? ORDER BY created_at DESC",
                (f"{date}%",)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM upvotes ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # --- daily reports ---

    def save_daily_report(self, report_date: str, karma: int, karma_change: int,
                          comments_count: int, posts_count: int, upvotes_count: int,
                          browsed_count: int, top_subreddit: str, risk_level: str,
                          strategy_notes: str = ""):
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT INTO daily_reports
               (report_date, karma, karma_change, comments_count, posts_count,
                upvotes_count, browsed_count, top_subreddit, risk_level, strategy_notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(report_date) DO UPDATE SET
                karma=?, karma_change=?, comments_count=?, posts_count=?,
                upvotes_count=?, browsed_count=?, top_subreddit=?, risk_level=?,
                strategy_notes=?, created_at=?""",
            (report_date, karma, karma_change, comments_count, posts_count,
             upvotes_count, browsed_count, top_subreddit, risk_level, strategy_notes, now,
             karma, karma_change, comments_count, posts_count,
             upvotes_count, browsed_count, top_subreddit, risk_level, strategy_notes, now),
        )
        self.conn.commit()

    def get_daily_reports(self, limit: int = 30) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM daily_reports ORDER BY report_date DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_daily_report(self, date: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM daily_reports WHERE report_date = ?", (date,)
        ).fetchone()
        return dict(row) if row else None

    # --- karma history ---

    def save_karma(self, karma: int):
        self.conn.execute(
            "INSERT INTO karma_history (karma, recorded_at) VALUES (?, ?)",
            (karma, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_karma_history(self, limit: int = 30) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM karma_history ORDER BY recorded_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_karma(self) -> int:
        row = self.conn.execute(
            "SELECT karma FROM karma_history ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()
        return row["karma"] if row else 0

    # --- strategy log ---

    def save_strategy(self, strategy_type: str, subreddit: str,
                      recommendation: str, reason: str, priority: int = 0):
        self.conn.execute(
            """INSERT INTO strategy_log (strategy_type, subreddit, recommendation, reason, priority, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (strategy_type, subreddit, recommendation, reason, priority, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_strategies(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM strategy_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- activity summary ---

    def get_activity_summary(self, date: str | None = None) -> dict:
        """날짜별 활동 요약."""
        date_filter = f" WHERE created_at LIKE '{date}%'" if date else ""
        date_filter_b = f" WHERE browsed_at LIKE '{date}%'" if date else ""
        date_filter_p = f" WHERE posted_at LIKE '{date}%'" if date else ""

        comments_total = self.conn.execute(
            f"SELECT COUNT(*) as cnt FROM comments{date_filter}"
        ).fetchone()["cnt"]

        comments_by_type = self.conn.execute(
            f"SELECT comment_type, COUNT(*) as cnt FROM comments{date_filter} GROUP BY comment_type"
        ).fetchall()

        comments_by_sub = self.conn.execute(
            f"SELECT subreddit, COUNT(*) as cnt FROM comments{date_filter} GROUP BY subreddit ORDER BY cnt DESC"
        ).fetchall()

        posts_total = self.conn.execute(
            f"SELECT COUNT(*) as cnt FROM submissions{date_filter_p}"
        ).fetchone()["cnt"]

        browsed_total = self.conn.execute(
            f"SELECT COUNT(*) as cnt FROM browsed_posts{date_filter_b}"
        ).fetchone()["cnt"]

        upvotes_total = self.conn.execute(
            f"SELECT COUNT(*) as cnt FROM upvotes{date_filter}"
        ).fetchone()["cnt"]

        activity_log_rows = self.conn.execute(
            f"SELECT action_type, COUNT(*) as cnt FROM activity_log{date_filter} GROUP BY action_type"
        ).fetchall()

        return {
            "comments_total": comments_total,
            "comments_by_type": [dict(r) for r in comments_by_type],
            "comments_by_sub": [dict(r) for r in comments_by_sub],
            "posts_total": posts_total,
            "browsed_total": browsed_total,
            "upvotes_total": upvotes_total,
            "activity_by_type": [dict(r) for r in activity_log_rows],
        }

    # --- custom schedule ---

    def get_custom_schedule(self, day: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM custom_schedule WHERE day = ?", (day,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_custom_schedules(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM custom_schedule ORDER BY day"
        ).fetchall()
        return [dict(r) for r in rows]

    def save_custom_schedule(self, day: int, phase: str, description: str, tasks_json: str):
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT INTO custom_schedule (day, phase, description, tasks_json, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(day) DO UPDATE SET phase=?, description=?, tasks_json=?, updated_at=?""",
            (day, phase, description, tasks_json, now,
             phase, description, tasks_json, now),
        )
        self.conn.commit()

    def delete_custom_schedule(self, day: int):
        self.conn.execute("DELETE FROM custom_schedule WHERE day = ?", (day,))
        self.conn.commit()

    # --- campaign config (캠페인별 격리) ---

    def has_commented_on(self, submission_id: str) -> bool:
        """이 포스트에 이미 댓글을 달았는지 확인."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM comments WHERE submission_id = ?",
            (submission_id,),
        ).fetchone()
        return row["cnt"] > 0

    def has_posted_to(self, subreddit: str, days: int = 7) -> bool:
        """최근 N일 내 이 서브레딧에 포스트했는지 확인."""
        row = self.conn.execute(
            """SELECT COUNT(*) as cnt FROM submissions
               WHERE subreddit = ? AND posted_at >= datetime('now', ?)""",
            (subreddit, f"-{days} days"),
        ).fetchone()
        return row["cnt"] > 0

    def get_today_action_count(self, action_type: str) -> int:
        """오늘 특정 타입의 액션 수."""
        today = datetime.now().strftime("%Y-%m-%d")
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM comments WHERE comment_type = ? AND created_at LIKE ?",
            (action_type, f"{today}%"),
        ).fetchone()
        return row["cnt"]

    def get_today_post_count(self) -> int:
        """오늘 포스트 수."""
        today = datetime.now().strftime("%Y-%m-%d")
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM submissions WHERE posted_at LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return row["cnt"]

    def get_commented_submission_ids(self) -> set[str]:
        """댓글 작성한 모든 submission_id."""
        rows = self.conn.execute(
            "SELECT DISTINCT submission_id FROM comments WHERE submission_id IS NOT NULL"
        ).fetchall()
        return {r["submission_id"] for r in rows}

    def get_posted_subreddits(self, days: int = 30) -> set[str]:
        """최근 N일 내 포스트한 서브레딧."""
        rows = self.conn.execute(
            """SELECT DISTINCT subreddit FROM submissions
               WHERE posted_at >= datetime('now', ?)""",
            (f"-{days} days",),
        ).fetchall()
        return {r["subreddit"] for r in rows}

    def close(self):
        self.conn.close()
