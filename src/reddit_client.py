"""PRAW 래퍼 — Reddit API 호출."""

from __future__ import annotations

import time

import praw
from praw.models import Submission

from .config import Config


class RedditClient:
    def __init__(self, config: Config):
        self.config = config
        self.reddit = praw.Reddit(
            client_id=config.reddit.client_id,
            client_secret=config.reddit.client_secret,
            username=config.reddit.username,
            password=config.reddit.password,
            user_agent=config.reddit.user_agent,
        )
        self.delay = config.settings.comment_delay

    def verify_auth(self) -> str:
        """인증 확인, 사용자명 반환."""
        return str(self.reddit.user.me())

    def submit_post(self, subreddit: str, title: str, body: str) -> Submission:
        """서브레딧에 텍스트 포스트 제출."""
        sub = self.reddit.subreddit(subreddit.removeprefix("r/"))
        submission = sub.submit(title=title, selftext=body)
        return submission

    def post_comment(self, submission_id: str, body: str) -> praw.models.Comment:
        """포스트에 댓글 작성."""
        submission = self.reddit.submission(id=submission_id)
        comment = submission.reply(body)
        time.sleep(self.delay)
        return comment

    def reply_to_comment(self, comment_id: str, body: str) -> praw.models.Comment:
        """댓글에 답글 작성."""
        comment = self.reddit.comment(id=comment_id)
        reply = comment.reply(body)
        time.sleep(self.delay)
        return reply

    def get_submission(self, submission_id: str) -> Submission:
        """submission 조회."""
        return self.reddit.submission(id=submission_id)

    def get_new_comments(self, submission_id: str) -> list[praw.models.Comment]:
        """포스트의 모든 댓글 가져오기."""
        submission = self.reddit.submission(id=submission_id)
        submission.comments.replace_more(limit=0)
        return list(submission.comments.list())

    def search_subreddit(
        self, subreddit: str, query: str, limit: int = 10
    ) -> list[Submission]:
        """서브레딧에서 관련 글 검색."""
        sub = self.reddit.subreddit(subreddit.removeprefix("r/"))
        return list(sub.search(query, sort="new", time_filter="week", limit=limit))

    def get_hot_posts(self, subreddit: str, limit: int = 10) -> list[Submission]:
        """서브레딧 인기 글 조회."""
        sub = self.reddit.subreddit(subreddit.removeprefix("r/"))
        return list(sub.hot(limit=limit))

    def get_submission_metrics(self, submission_id: str) -> dict:
        """submission 메트릭 조회."""
        s = self.reddit.submission(id=submission_id)
        return {
            "upvotes": s.score,
            "upvote_ratio": s.upvote_ratio,
            "comment_count": s.num_comments,
            "url": f"https://reddit.com{s.permalink}",
        }
