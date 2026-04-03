"""Reddit Campaign 웹 대시보드 — 브라우저에서 캠페인 관리 + 활동 내역 조회."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from .state import StateDB

DB_PATH = "data/campaign.db"

# 캠페인 실행 상태 (글로벌)
_campaign_runner = {"running": False, "thread": None, "log": [], "current_day": 0}


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/" or path == "/dashboard":
            self._serve_html()
        elif path == "/api/summary":
            self._api_summary(params)
        elif path == "/api/comments":
            self._api_comments(params)
        elif path == "/api/posts":
            self._api_posts(params)
        elif path == "/api/browsed":
            self._api_browsed(params)
        elif path == "/api/upvotes":
            self._api_upvotes(params)
        elif path == "/api/campaign":
            self._api_campaign()
        elif path == "/api/activity-log":
            self._api_activity_log(params)
        elif path == "/api/daily-reports":
            self._api_daily_reports(params)
        elif path == "/api/karma-history":
            self._api_karma_history(params)
        elif path == "/api/strategies":
            self._api_strategies(params)
        elif path == "/api/generate-report":
            self._api_generate_report(params)
        elif path == "/api/campaign-config":
            self._api_campaign_config()
        elif path == "/api/schedule":
            self._api_schedule()
        elif path == "/api/runner-status":
            self._api_runner_status()
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}

        if path == "/api/campaign-config":
            self._api_save_campaign_config(data)
        elif path == "/api/run-campaign":
            self._api_run_campaign(data)
        elif path == "/api/stop-campaign":
            self._api_stop_campaign()
        elif path == "/api/reset-day":
            self._api_reset_day(data)
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json_response(self, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _api_summary(self, params):
        date = params.get("date", [None])[0]
        db = StateDB(DB_PATH)
        today = db.get_activity_summary(date or datetime.now().strftime("%Y-%m-%d"))
        total = db.get_activity_summary()
        db.close()
        self._json_response({"today": today, "all_time": total, "date": date or datetime.now().strftime("%Y-%m-%d")})

    def _api_comments(self, params):
        comment_type = params.get("type", [None])[0]
        db = StateDB(DB_PATH)
        comments = db.get_comments(comment_type)
        db.close()
        self._json_response(comments)

    def _api_posts(self, params):
        db = StateDB(DB_PATH)
        posts = db.get_submissions()
        db.close()
        self._json_response(posts)

    def _api_browsed(self, params):
        date = params.get("date", [None])[0]
        db = StateDB(DB_PATH)
        browsed = db.get_browsed_posts(date)
        db.close()
        self._json_response(browsed)

    def _api_upvotes(self, params):
        date = params.get("date", [None])[0]
        db = StateDB(DB_PATH)
        upvotes = db.get_upvotes(date)
        db.close()
        self._json_response(upvotes)

    def _api_campaign(self):
        db = StateDB(DB_PATH)
        statuses = db.get_all_day_statuses()
        db.close()
        self._json_response(statuses)

    def _api_activity_log(self, params):
        db = StateDB(DB_PATH)
        rows = db.conn.execute(
            "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        db.close()
        self._json_response([dict(r) for r in rows])

    def _api_daily_reports(self, params):
        limit = int(params.get("limit", [30])[0])
        db = StateDB(DB_PATH)
        reports = db.get_daily_reports(limit)
        db.close()
        self._json_response(reports)

    def _api_karma_history(self, params):
        limit = int(params.get("limit", [30])[0])
        db = StateDB(DB_PATH)
        history = db.get_karma_history(limit)
        db.close()
        self._json_response(history)

    def _api_strategies(self, params):
        limit = int(params.get("limit", [20])[0])
        db = StateDB(DB_PATH)
        strategies = db.get_strategies(limit)
        db.close()
        self._json_response(strategies)

    def _api_generate_report(self, params):
        karma = int(params.get("karma", [0])[0])
        from .strategy_advisor import generate_daily_report, suggest_next_day_strategy
        db = StateDB(DB_PATH)
        report = generate_daily_report(db, karma=karma)
        strategies = suggest_next_day_strategy(db)
        db.close()
        self._json_response({"report": report, "strategies": strategies})

    def _api_campaign_config(self):
        """캠페인 설정 조회."""
        try:
            from .campaign_config import load_campaign, campaign_exists, to_dict
            if campaign_exists():
                cfg = load_campaign()
                self._json_response({"exists": True, "config": to_dict(cfg)})
            else:
                self._json_response({"exists": False, "config": None})
        except Exception as e:
            self._json_response({"exists": False, "error": str(e)})

    def _api_save_campaign_config(self, data):
        """캠페인 설정 저장."""
        try:
            from .campaign_config import CampaignConfig, SubTarget, PostTarget, Limits, save_campaign

            cfg = CampaignConfig(
                product_name=data.get("product", {}).get("name", ""),
                product_url=data.get("product", {}).get("url", ""),
                tagline=data.get("product", {}).get("tagline", ""),
                category=data.get("product", {}).get("category", "developer_tool"),
                reddit_username=data.get("reddit", {}).get("username", ""),
                karma_subs=[
                    SubTarget(sub=s["sub"], keywords=s.get("keywords", []))
                    for s in data.get("targets", {}).get("karma_subs", [])
                ],
                seed_subs=[
                    SubTarget(sub=s["sub"], keywords=s.get("keywords", []))
                    for s in data.get("targets", {}).get("seed_subs", [])
                ],
                post_subs=[
                    PostTarget(sub=s["sub"], title_hint=s.get("title_hint", ""))
                    for s in data.get("targets", {}).get("post_subs", [])
                ],
                karma_tone=data.get("content", {}).get("karma_tone", "helpful_expert"),
                seed_tone=data.get("content", {}).get("seed_tone", "casual_mention"),
                limits=Limits(
                    karma_comments_per_day=data.get("limits", {}).get("karma_comments_per_day", 4),
                    seed_comments_per_day=data.get("limits", {}).get("seed_comments_per_day", 2),
                    posts_per_day=data.get("limits", {}).get("posts_per_day", 1),
                    min_delay_seconds=data.get("limits", {}).get("min_delay_seconds", 8),
                    max_delay_seconds=data.get("limits", {}).get("max_delay_seconds", 25),
                ),
            )
            save_campaign(cfg)
            self._json_response({"success": True})
        except Exception as e:
            self._json_response({"success": False, "error": str(e)})

    def _api_schedule(self):
        """30일 스케줄 조회."""
        try:
            from .campaign_config import load_campaign, campaign_exists
            from .schedule import build_schedule, build_schedule_from_config

            config = None
            if campaign_exists():
                config = load_campaign()

            schedule = build_schedule_from_config(config) if config else build_schedule()

            result = []
            for s in schedule:
                result.append({
                    "day": s.day,
                    "phase": s.phase.value,
                    "description": s.description,
                    "tasks": [
                        {
                            "type": t.task_type.value,
                            "subreddits": t.subreddits,
                            "keywords": t.search_keywords,
                            "max_comments": t.max_comments,
                            "post_subreddit": t.post_subreddit,
                            "notes": t.notes,
                        }
                        for t in s.tasks
                    ],
                })
            self._json_response(result)
        except Exception as e:
            self._json_response({"error": str(e)})

    def _api_run_campaign(self, data):
        """캠페인 실행 (백그라운드 스레드)."""
        global _campaign_runner

        if _campaign_runner["running"]:
            self._json_response({"success": False, "error": "이미 실행 중입니다"})
            return

        dry_run = data.get("dry_run", False)
        start_day = data.get("start_day")
        run_all = data.get("run_all", False)

        def run():
            global _campaign_runner
            _campaign_runner["running"] = True
            _campaign_runner["log"] = []
            try:
                from .autopilot_browser import run_browser_campaign
                run_browser_campaign(
                    db_path=DB_PATH,
                    run_all=run_all,
                    dry_run=dry_run,
                    start_day=start_day,
                )
            except Exception as e:
                _campaign_runner["log"].append(f"Error: {e}")
            finally:
                _campaign_runner["running"] = False

        t = threading.Thread(target=run, daemon=True)
        t.start()
        _campaign_runner["thread"] = t
        self._json_response({"success": True, "message": "캠페인 시작됨"})

    def _api_stop_campaign(self):
        """캠페인 중지."""
        global _campaign_runner
        _campaign_runner["running"] = False
        self._json_response({"success": True, "message": "중지 요청됨"})

    def _api_runner_status(self):
        """캠페인 실행 상태."""
        self._json_response({
            "running": _campaign_runner["running"],
            "log": _campaign_runner["log"][-50:],
        })

    def _api_reset_day(self, data):
        """특정 날 상태 리셋."""
        day_id = data.get("day_id", "")
        if not day_id:
            self._json_response({"success": False, "error": "day_id 필요"})
            return
        db = StateDB(DB_PATH)
        db.set_day_status(day_id, "pending")
        db.close()
        self._json_response({"success": True})

    def _serve_html(self):
        html = DASHBOARD_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, format, *args):
        pass


def run_web_dashboard(port: int = 8090):
    """웹 대시보드 서버 시작."""
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"Dashboard: http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reddit Campaign Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0f0f0f; color: #e0e0e0; }
.container { max-width: 1400px; margin: 0 auto; padding: 20px; }
h1 { font-size: 1.8em; margin-bottom: 5px; color: #ff4500; }
h2 { font-size: 1.2em; margin: 20px 0 10px; color: #aaa; border-bottom: 1px solid #333; padding-bottom: 5px; }
h3 { font-size: 1em; color: #888; margin: 12px 0 8px; }
.subtitle { color: #666; font-size: 0.9em; margin-bottom: 20px; }

/* Stats Cards */
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 20px; }
.stat-card { background: #1a1a1a; border-radius: 10px; padding: 16px; text-align: center; border: 1px solid #2a2a2a; }
.stat-card .number { font-size: 2em; font-weight: bold; color: #ff4500; }
.stat-card .label { font-size: 0.8em; color: #888; margin-top: 4px; }
.stat-card .sub { font-size: 0.7em; color: #555; }

/* Progress Bar */
.progress-bar { background: #1a1a1a; border-radius: 10px; padding: 16px; margin-bottom: 20px; border: 1px solid #2a2a2a; }
.progress-track { background: #2a2a2a; border-radius: 6px; height: 24px; overflow: hidden; margin-top: 8px; }
.progress-fill { background: linear-gradient(90deg, #ff4500, #ff6b35); height: 100%; border-radius: 6px;
                  transition: width 0.5s ease; display: flex; align-items: center; justify-content: center;
                  font-size: 0.75em; font-weight: bold; color: white; }

/* Day Grid */
.day-grid { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; }
.day-dot { width: 28px; height: 28px; border-radius: 4px; display: flex; align-items: center; justify-content: center;
           font-size: 0.6em; font-weight: bold; cursor: pointer; transition: all 0.2s; }
.day-dot:hover { transform: scale(1.2); }
.day-dot.completed { background: #1b5e20; color: #4caf50; }
.day-dot.in_progress { background: #33310a; color: #ffc107; }
.day-dot.error { background: #4a1010; color: #f44336; }
.day-dot.pending { background: #1a1a1a; color: #444; border: 1px solid #333; }

/* Tables */
table { width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 0.85em; }
th { background: #1a1a1a; color: #aaa; text-align: left; padding: 8px 12px; font-weight: 600;
     border-bottom: 2px solid #333; }
td { padding: 8px 12px; border-bottom: 1px solid #222; vertical-align: top; }
tr:hover td { background: #1a1a1a; }

/* Tags */
.tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 600; }
.tag-karma { background: #1b3a1b; color: #4caf50; }
.tag-seeding { background: #1b2e3a; color: #2196f3; }
.tag-reply { background: #3a2e1b; color: #ff9800; }
.tag-post { background: #3a1b1b; color: #f44336; }

/* Comment body */
.comment-body { color: #999; font-size: 0.85em; margin-top: 4px; line-height: 1.4; }

/* Tabs */
.tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
.tab { padding: 8px 18px; background: #1a1a1a; border: 1px solid #333; border-radius: 6px;
       cursor: pointer; font-size: 0.85em; color: #aaa; transition: all 0.2s; }
.tab:hover { border-color: #ff4500; color: #ff4500; }
.tab.active { background: #ff4500; color: white; border-color: #ff4500; }

.tab-content { display: none; }
.tab-content.active { display: block; }

/* Date picker */
.date-picker { margin-bottom: 16px; display: flex; align-items: center; gap: 10px; }
.date-picker input { background: #1a1a1a; border: 1px solid #333; color: #e0e0e0; padding: 6px 12px;
                      border-radius: 6px; font-size: 0.9em; }
.date-picker button { background: #ff4500; color: white; border: none; padding: 6px 16px;
                       border-radius: 6px; cursor: pointer; font-size: 0.85em; }

.url-link { color: #4a9eff; text-decoration: none; font-size: 0.8em; }
.url-link:hover { text-decoration: underline; }

/* Campaign Config Form */
.form-section { background: #1a1a1a; border-radius: 10px; padding: 20px; margin-bottom: 16px; border: 1px solid #2a2a2a; }
.form-row { display: flex; gap: 12px; margin-bottom: 12px; align-items: center; }
.form-row label { min-width: 120px; color: #888; font-size: 0.85em; }
.form-row input, .form-row select { background: #0f0f0f; border: 1px solid #333; color: #e0e0e0;
  padding: 8px 12px; border-radius: 6px; font-size: 0.85em; flex: 1; }
.form-row input:focus, .form-row select:focus { border-color: #ff4500; outline: none; }
textarea.form-textarea { background: #0f0f0f; border: 1px solid #333; color: #e0e0e0;
  padding: 8px 12px; border-radius: 6px; font-size: 0.85em; width: 100%; min-height: 60px; resize: vertical; }

/* Buttons */
.btn { padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85em; font-weight: 600;
       transition: all 0.2s; }
.btn-primary { background: #ff4500; color: white; }
.btn-primary:hover { background: #e63e00; }
.btn-secondary { background: #333; color: #ddd; }
.btn-secondary:hover { background: #444; }
.btn-danger { background: #c62828; color: white; }
.btn-danger:hover { background: #b71c1c; }
.btn-success { background: #2e7d32; color: white; }
.btn-success:hover { background: #1b5e20; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-group { display: flex; gap: 8px; margin-top: 12px; }

/* Runner Status */
.runner-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 12px;
                font-size: 0.8em; font-weight: 600; }
.runner-badge.running { background: #1b3a1b; color: #4caf50; }
.runner-badge.stopped { background: #2a2a2a; color: #666; }

/* Schedule Table */
.schedule-grid { display: grid; grid-template-columns: 50px 100px 1fr 1fr; gap: 1px; font-size: 0.82em; }
.schedule-cell { padding: 6px 10px; background: #1a1a1a; }
.schedule-header { background: #222; color: #aaa; font-weight: 600; }
.phase-badge { padding: 2px 6px; border-radius: 3px; font-size: 0.75em; }
.phase-karma_build { background: #1b3a1b; color: #4caf50; }
.phase-light_seed { background: #1b2e3a; color: #2196f3; }
.phase-seed_and_post { background: #3a2e1b; color: #ff9800; }
.phase-full_campaign { background: #3a1b1b; color: #f44336; }

/* Sub list editor */
.sub-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.sub-chip { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; background: #222; border-radius: 12px;
            font-size: 0.8em; color: #ccc; border: 1px solid #333; }
.sub-chip .remove { cursor: pointer; color: #f44336; font-weight: bold; }
.sub-chip .remove:hover { color: #ff5252; }
</style>
</head>
<body>
<div class="container">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
    <div>
      <h1>Reddit Campaign Dashboard</h1>
      <div class="subtitle" id="date-label"></div>
    </div>
    <div id="runner-badge"></div>
  </div>

  <div class="date-picker">
    <input type="date" id="date-input">
    <button onclick="loadDate()">Filter</button>
    <button onclick="loadToday()">Today</button>
  </div>

  <!-- Stats Cards -->
  <div class="stats" id="stats-cards"></div>

  <!-- Campaign Progress -->
  <div class="progress-bar" id="campaign-progress"></div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" onclick="switchTab('campaign-mgr')">Campaign</div>
    <div class="tab" onclick="switchTab('schedule')">Schedule</div>
    <div class="tab" onclick="switchTab('comments')">Comments</div>
    <div class="tab" onclick="switchTab('browsed')">Browsed</div>
    <div class="tab" onclick="switchTab('upvotes')">Upvotes</div>
    <div class="tab" onclick="switchTab('posts')">Posts</div>
    <div class="tab" onclick="switchTab('activity')">Activity Log</div>
    <div class="tab" onclick="switchTab('reports')">Daily Reports</div>
    <div class="tab" onclick="switchTab('strategy')">Strategy</div>
  </div>

  <div id="tab-campaign-mgr" class="tab-content active"></div>
  <div id="tab-schedule" class="tab-content"></div>
  <div id="tab-comments" class="tab-content"></div>
  <div id="tab-browsed" class="tab-content"></div>
  <div id="tab-upvotes" class="tab-content"></div>
  <div id="tab-posts" class="tab-content"></div>
  <div id="tab-activity" class="tab-content"></div>
  <div id="tab-reports" class="tab-content"></div>
  <div id="tab-strategy" class="tab-content"></div>
</div>

<script>
const API = '';
let currentDate = new Date().toISOString().slice(0, 10);
let campaignConfig = null;

document.getElementById('date-input').value = currentDate;
document.getElementById('date-label').textContent = `Date: ${currentDate}`;

async function fetchJSON(url) {
  const res = await fetch(API + url);
  return res.json();
}

async function postJSON(url, data) {
  const res = await fetch(API + url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  return res.json();
}

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}

function loadDate() {
  currentDate = document.getElementById('date-input').value;
  document.getElementById('date-label').textContent = `Date: ${currentDate}`;
  loadAll();
}

function loadToday() {
  currentDate = new Date().toISOString().slice(0, 10);
  document.getElementById('date-input').value = currentDate;
  document.getElementById('date-label').textContent = `Date: ${currentDate}`;
  loadAll();
}

function tagHTML(type) {
  const map = {
    karma_build: ['KARMA', 'tag-karma'],
    seeding: ['SEED', 'tag-seeding'],
    auto_reply: ['REPLY', 'tag-reply'],
    reply: ['REPLY', 'tag-reply'],
    post: ['POST', 'tag-post'],
  };
  const [label, cls] = map[type] || [type || '?', ''];
  return `<span class="tag ${cls}">${label}</span>`;
}

function timeStr(iso) {
  if (!iso) return '-';
  return iso.replace('T', ' ').slice(0, 16);
}

// ═══ Campaign Management Tab ═══

async function loadCampaignConfig() {
  const data = await fetchJSON('/api/campaign-config');
  campaignConfig = data.config;

  const el = document.getElementById('tab-campaign-mgr');
  if (!data.exists || !campaignConfig) {
    el.innerHTML = `
      <div class="form-section">
        <h3>Campaign Not Configured</h3>
        <p style="color:#888;margin:12px 0">campaign.toml이 없습니다. 아래에서 새 캠페인을 설정하세요.</p>
        ${renderCampaignForm({
          product: {name:'', url:'', tagline:'', category:'developer_tool'},
          reddit: {username:''},
          targets: {karma_subs:[], seed_subs:[], post_subs:[]},
          content: {karma_tone:'helpful_expert', seed_tone:'casual_mention'},
          limits: {karma_comments_per_day:4, seed_comments_per_day:2, posts_per_day:1, min_delay_seconds:8, max_delay_seconds:25}
        })}
      </div>`;
  } else {
    el.innerHTML = `
      <div style="display:flex;gap:16px;margin-bottom:16px">
        <div class="form-section" style="flex:1">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h3 style="margin:0">${campaignConfig.product.name || 'Untitled Campaign'}</h3>
            <span style="color:#666;font-size:0.8em">${campaignConfig.product.category}</span>
          </div>
          <p style="color:#aaa;margin:8px 0">${campaignConfig.product.tagline || ''}</p>
          ${campaignConfig.product.url ? `<a href="${campaignConfig.product.url}" target="_blank" class="url-link">${campaignConfig.product.url}</a>` : ''}

          <div style="margin-top:16px;display:flex;gap:20px">
            <div><span style="color:#666">Reddit:</span> <span style="color:#4a9eff">u/${campaignConfig.reddit.username || '?'}</span></div>
            <div><span style="color:#666">Karma tone:</span> ${campaignConfig.content.karma_tone}</div>
            <div><span style="color:#666">Seed tone:</span> ${campaignConfig.content.seed_tone}</div>
          </div>

          <div style="margin-top:12px">
            <span style="color:#666">Karma subs:</span>
            <div class="sub-list">${(campaignConfig.targets.karma_subs||[]).map(s => `<span class="sub-chip">r/${s.sub}</span>`).join('')}</div>
          </div>
          <div style="margin-top:8px">
            <span style="color:#666">Seed subs:</span>
            <div class="sub-list">${(campaignConfig.targets.seed_subs||[]).map(s => `<span class="sub-chip">r/${s.sub}</span>`).join('')}</div>
          </div>
          <div style="margin-top:8px">
            <span style="color:#666">Post subs:</span>
            <div class="sub-list">${(campaignConfig.targets.post_subs||[]).map(s => `<span class="sub-chip">r/${s.sub}</span>`).join('')}</div>
          </div>

          <div style="margin-top:12px;color:#666;font-size:0.85em">
            Limits: ${campaignConfig.limits.karma_comments_per_day} karma/day, ${campaignConfig.limits.seed_comments_per_day} seed/day,
            ${campaignConfig.limits.posts_per_day} post/day | Delay: ${campaignConfig.limits.min_delay_seconds}-${campaignConfig.limits.max_delay_seconds}s
          </div>
        </div>

        <div class="form-section" style="width:300px">
          <h3 style="margin:0 0 12px">Controls</h3>
          <div class="btn-group" style="flex-direction:column">
            <button class="btn btn-primary" onclick="runCampaign(false, false)" id="btn-run-next">Run Next Day</button>
            <button class="btn btn-secondary" onclick="runCampaign(false, true)">Dry Run (Next Day)</button>
            <button class="btn btn-success" onclick="runCampaign(true, false)">Run All Remaining</button>
            <button class="btn btn-danger" onclick="stopCampaign()" id="btn-stop" disabled>Stop Campaign</button>
          </div>
          <div style="margin-top:16px">
            <label style="color:#666;font-size:0.85em">Start from day:</label>
            <input type="number" id="start-day-input" min="1" max="30" value="" placeholder="auto"
                   style="width:80px;background:#0f0f0f;border:1px solid #333;color:#e0e0e0;padding:4px 8px;border-radius:4px">
          </div>
        </div>
      </div>

      <div class="form-section">
        <div style="display:flex;justify-content:space-between;align-items:center;cursor:pointer" onclick="toggleEditForm()">
          <h3 style="margin:0">Edit Campaign Config</h3>
          <span id="edit-toggle" style="color:#666">&#9660;</span>
        </div>
        <div id="edit-form" style="display:none;margin-top:16px">
          ${renderCampaignForm(campaignConfig)}
        </div>
      </div>`;
  }
}

function toggleEditForm() {
  const el = document.getElementById('edit-form');
  const toggle = document.getElementById('edit-toggle');
  if (el.style.display === 'none') {
    el.style.display = 'block';
    toggle.innerHTML = '&#9650;';
  } else {
    el.style.display = 'none';
    toggle.innerHTML = '&#9660;';
  }
}

function renderCampaignForm(cfg) {
  return `
    <h3>Product</h3>
    <div class="form-row"><label>Name</label><input id="cfg-name" value="${cfg.product.name}"></div>
    <div class="form-row"><label>URL</label><input id="cfg-url" value="${cfg.product.url}"></div>
    <div class="form-row"><label>Tagline</label><input id="cfg-tagline" value="${cfg.product.tagline}"></div>
    <div class="form-row"><label>Category</label>
      <select id="cfg-category">
        ${['developer_tool','saas','app','service','community'].map(c =>
          `<option value="${c}" ${cfg.product.category===c?'selected':''}>${c}</option>`
        ).join('')}
      </select>
    </div>

    <h3>Reddit</h3>
    <div class="form-row"><label>Username</label><input id="cfg-username" value="${cfg.reddit.username}"></div>

    <h3>Karma Subreddits</h3>
    <div class="form-row"><label>Subs (comma)</label>
      <input id="cfg-karma-subs" value="${(cfg.targets.karma_subs||[]).map(s=>s.sub).join(', ')}">
    </div>

    <h3>Seed Subreddits</h3>
    <div class="form-row"><label>Subs (comma)</label>
      <input id="cfg-seed-subs" value="${(cfg.targets.seed_subs||[]).map(s=>s.sub).join(', ')}">
    </div>

    <h3>Post Subreddits</h3>
    <div class="form-row"><label>Subs (comma)</label>
      <input id="cfg-post-subs" value="${(cfg.targets.post_subs||[]).map(s=>s.sub).join(', ')}">
    </div>

    <h3>Content Style</h3>
    <div class="form-row"><label>Karma Tone</label>
      <select id="cfg-karma-tone">
        ${['helpful_expert','friendly_user','curious_learner'].map(t =>
          `<option value="${t}" ${cfg.content.karma_tone===t?'selected':''}>${t}</option>`
        ).join('')}
      </select>
    </div>
    <div class="form-row"><label>Seed Tone</label>
      <select id="cfg-seed-tone">
        ${['casual_mention','experience_share','comparison'].map(t =>
          `<option value="${t}" ${cfg.content.seed_tone===t?'selected':''}>${t}</option>`
        ).join('')}
      </select>
    </div>

    <h3>Limits</h3>
    <div class="form-row">
      <label>Karma/day</label><input type="number" id="cfg-karma-limit" value="${cfg.limits.karma_comments_per_day}" style="width:80px">
      <label>Seed/day</label><input type="number" id="cfg-seed-limit" value="${cfg.limits.seed_comments_per_day}" style="width:80px">
      <label>Posts/day</label><input type="number" id="cfg-post-limit" value="${cfg.limits.posts_per_day}" style="width:80px">
    </div>
    <div class="form-row">
      <label>Min delay (s)</label><input type="number" id="cfg-min-delay" value="${cfg.limits.min_delay_seconds}" style="width:80px">
      <label>Max delay (s)</label><input type="number" id="cfg-max-delay" value="${cfg.limits.max_delay_seconds}" style="width:80px">
    </div>

    <div class="btn-group">
      <button class="btn btn-primary" onclick="saveCampaignConfig()">Save Campaign Config</button>
    </div>`;
}

async function saveCampaignConfig() {
  const parseSubs = (id) => document.getElementById(id).value.split(',').map(s => s.trim()).filter(Boolean).map(s => ({sub: s, keywords: []}));
  const parsePostSubs = (id) => document.getElementById(id).value.split(',').map(s => s.trim()).filter(Boolean).map(s => ({sub: s, title_hint: ''}));

  const cfg = {
    product: {
      name: document.getElementById('cfg-name').value,
      url: document.getElementById('cfg-url').value,
      tagline: document.getElementById('cfg-tagline').value,
      category: document.getElementById('cfg-category').value,
    },
    reddit: { username: document.getElementById('cfg-username').value },
    targets: {
      karma_subs: parseSubs('cfg-karma-subs'),
      seed_subs: parseSubs('cfg-seed-subs'),
      post_subs: parsePostSubs('cfg-post-subs'),
    },
    content: {
      karma_tone: document.getElementById('cfg-karma-tone').value,
      seed_tone: document.getElementById('cfg-seed-tone').value,
    },
    limits: {
      karma_comments_per_day: parseInt(document.getElementById('cfg-karma-limit').value) || 4,
      seed_comments_per_day: parseInt(document.getElementById('cfg-seed-limit').value) || 2,
      posts_per_day: parseInt(document.getElementById('cfg-post-limit').value) || 1,
      min_delay_seconds: parseInt(document.getElementById('cfg-min-delay').value) || 8,
      max_delay_seconds: parseInt(document.getElementById('cfg-max-delay').value) || 25,
    },
  };

  const result = await postJSON('/api/campaign-config', cfg);
  if (result.success) {
    alert('Campaign config saved!');
    loadCampaignConfig();
  } else {
    alert('Save failed: ' + (result.error || 'unknown'));
  }
}

async function runCampaign(runAll, dryRun) {
  const startDay = document.getElementById('start-day-input')?.value;
  const data = {
    run_all: runAll,
    dry_run: dryRun,
    start_day: startDay ? parseInt(startDay) : null,
  };
  const result = await postJSON('/api/run-campaign', data);
  if (result.success) {
    document.getElementById('btn-run-next').disabled = true;
    document.getElementById('btn-stop').disabled = false;
    alert(dryRun ? 'Dry run started!' : 'Campaign started!');
  } else {
    alert('Failed: ' + (result.error || 'unknown'));
  }
}

async function stopCampaign() {
  await postJSON('/api/stop-campaign', {});
  document.getElementById('btn-run-next').disabled = false;
  document.getElementById('btn-stop').disabled = true;
  alert('Stop requested');
}

async function resetDay(dayId) {
  if (!confirm(`Reset ${dayId} to pending?`)) return;
  await postJSON('/api/reset-day', {day_id: dayId});
  loadAll();
}

// ═══ Schedule Tab ═══

async function loadSchedule() {
  const schedule = await fetchJSON('/api/schedule');
  if (schedule.error) {
    document.getElementById('tab-schedule').innerHTML = `<p style="color:#f44336">${schedule.error}</p>`;
    return;
  }

  let currentPhase = '';
  let html = '';
  for (const s of schedule) {
    if (s.phase !== currentPhase) {
      currentPhase = s.phase;
      const phaseNames = {
        karma_build: 'Phase 1: Karma Building',
        light_seed: 'Phase 2: Karma + Light Seeding',
        seed_and_post: 'Phase 3: Seeding + First Posts',
        full_campaign: 'Phase 4: Full Campaign',
      };
      html += `<h3 style="margin-top:16px"><span class="phase-badge phase-${s.phase}">${phaseNames[s.phase] || s.phase}</span></h3>`;
    }

    const taskIcons = s.tasks.map(t => {
      const icons = {karma_comment:'K', seed_comment:'S', post:'P', monitor:'M', rest:'R', review:'V'};
      const colors = {karma_comment:'#4caf50', seed_comment:'#2196f3', post:'#f44336', monitor:'#ff9800', rest:'#666', review:'#9c27b0'};
      return `<span style="color:${colors[t.type]||'#888'};font-weight:bold" title="${t.notes||t.type}">${icons[t.type]||'?'}</span>`;
    }).join(' ');

    const subs = s.tasks.flatMap(t => t.subreddits || []).map(s => `r/${s}`).join(', ');
    const postSub = s.tasks.find(t => t.post_subreddit)?.post_subreddit;

    html += `<div style="display:flex;align-items:center;gap:12px;padding:6px 12px;background:#1a1a1a;margin:2px 0;border-radius:4px;font-size:0.85em">
      <span style="color:#666;min-width:50px">Day ${s.day}</span>
      <span style="min-width:60px">${taskIcons}</span>
      <span style="color:#ddd;flex:1">${s.description}</span>
      ${subs ? `<span style="color:#4a9eff;font-size:0.8em">${subs}</span>` : ''}
      ${postSub ? `<span class="tag tag-post">POST r/${postSub}</span>` : ''}
    </div>`;
  }

  document.getElementById('tab-schedule').innerHTML = html;
}

// ═══ Runner Status ═══

async function loadRunnerStatus() {
  const status = await fetchJSON('/api/runner-status');
  const badge = document.getElementById('runner-badge');
  if (status.running) {
    badge.innerHTML = '<span class="runner-badge running">&#9679; Running</span>';
    if (document.getElementById('btn-run-next')) document.getElementById('btn-run-next').disabled = true;
    if (document.getElementById('btn-stop')) document.getElementById('btn-stop').disabled = false;
  } else {
    badge.innerHTML = '<span class="runner-badge stopped">&#9679; Stopped</span>';
    if (document.getElementById('btn-run-next')) document.getElementById('btn-run-next').disabled = false;
    if (document.getElementById('btn-stop')) document.getElementById('btn-stop').disabled = true;
  }
}

// ═══ Load All ═══

async function loadAll() {
  // Summary
  const summary = await fetchJSON(`/api/summary?date=${currentDate}`);
  const t = summary.today, a = summary.all_time;
  document.getElementById('stats-cards').innerHTML = `
    <div class="stat-card"><div class="number">${t.comments_total}</div><div class="label">Comments Today</div><div class="sub">All: ${a.comments_total}</div></div>
    <div class="stat-card"><div class="number">${t.posts_total}</div><div class="label">Posts Today</div><div class="sub">All: ${a.posts_total}</div></div>
    <div class="stat-card"><div class="number">${t.browsed_total}</div><div class="label">Browsed Today</div><div class="sub">All: ${a.browsed_total}</div></div>
    <div class="stat-card"><div class="number">${t.upvotes_total}</div><div class="label">Upvotes Today</div><div class="sub">All: ${a.upvotes_total}</div></div>
    ${a.comments_by_type.map(r => `<div class="stat-card"><div class="number">${r.cnt}</div><div class="label">${r.comment_type || '?'}</div><div class="sub">type</div></div>`).join('')}
  `;

  // Campaign Progress
  const campaign = await fetchJSON('/api/campaign');
  const statusMap = {};
  campaign.forEach(s => statusMap[s.day_id] = s.status);
  const days = Array.from({length:30}, (_,i)=>`day-${String(i+1).padStart(2,'0')}`);
  const completed = days.filter(d => statusMap[d] === 'completed').length;
  const pct = Math.round(completed / days.length * 100);
  document.getElementById('campaign-progress').innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center">
      <span>Campaign Progress</span><span>${completed}/${days.length} days (${pct}%)</span>
    </div>
    <div class="progress-track"><div class="progress-fill" style="width:${pct}%">${pct}%</div></div>
    <div class="day-grid">${days.map(d => {
      const st = statusMap[d] || 'pending';
      const num = d.slice(-2);
      return `<div class="day-dot ${st}" title="${d}: ${st}" onclick="${st!=='pending'?`resetDay('${d}')`:''}">
        ${num}
      </div>`;
    }).join('')}</div>
  `;

  // Comments
  const comments = await fetchJSON('/api/comments');
  document.getElementById('tab-comments').innerHTML = comments.length === 0
    ? '<p style="color:#666">No comments yet.</p>'
    : comments.slice().reverse().map((c,i) => {
      const postLink = c.submission_id ? `https://www.reddit.com/comments/${c.submission_id}` : '';
      return `<div style="background:#1a1a1a;border-radius:10px;padding:16px;margin-bottom:12px;border:1px solid #2a2a2a">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <div style="display:flex;align-items:center;gap:8px">
            ${tagHTML(c.comment_type)}
            <span style="color:#4a9eff;font-weight:600">r/${c.subreddit||'?'}</span>
          </div>
          <span style="color:#666;font-size:0.8em">${timeStr(c.created_at)}</span>
        </div>
        <div style="color:#ddd;line-height:1.6;margin-bottom:10px;white-space:pre-wrap">${c.body||''}</div>
        <div style="display:flex;gap:12px">
          ${postLink ? `<a class="url-link" href="${postLink}" target="_blank">View post</a>` : ''}
        </div>
      </div>`;
    }).join('');

  // Browsed
  const browsed = await fetchJSON(`/api/browsed?date=${currentDate}`);
  document.getElementById('tab-browsed').innerHTML = browsed.length === 0
    ? '<p style="color:#666">No browsed posts.</p>'
    : browsed.map(b => {
      const url = b.url || '';
      return `<div style="background:#1a1a1a;border-radius:10px;padding:14px;margin-bottom:8px;border:1px solid #2a2a2a;display:flex;justify-content:space-between;align-items:center">
        <div style="flex:1">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="color:#4a9eff;font-weight:600">r/${b.subreddit||'?'}</span>
            <span style="color:#666;font-size:0.8em">u/${b.author||'?'}</span>
            <span style="color:#666;font-size:0.75em">${timeStr(b.browsed_at)}</span>
          </div>
          ${url ? `<a href="${url}" target="_blank" style="color:#ddd;text-decoration:none;font-size:0.95em">${b.title||'untitled'}</a>` : `<span style="color:#ddd">${b.title||'untitled'}</span>`}
        </div>
        <div style="display:flex;gap:16px;align-items:center;margin-left:16px">
          <span style="color:#ff4500;font-weight:bold" title="Score">${b.score||0}</span>
          <span style="color:#999" title="Comments">${b.comment_count||0}</span>
        </div>
      </div>`;
    }).join('');

  // Upvotes
  const upvotes = await fetchJSON(`/api/upvotes?date=${currentDate}`);
  document.getElementById('tab-upvotes').innerHTML = upvotes.length === 0
    ? '<p style="color:#666">No upvotes given yet.</p>'
    : `<table><thead><tr><th>Time</th><th>Type</th><th>Subreddit</th><th>Title</th></tr></thead><tbody>
      ${upvotes.map(u => `<tr>
        <td style="white-space:nowrap">${timeStr(u.created_at)}</td>
        <td>${u.target_type||'?'}</td>
        <td>r/${u.subreddit||'?'}</td>
        <td>${u.url ? `<a class="url-link" href="${u.url}" target="_blank">${(u.title||'').slice(0,50)}</a>` : (u.title||'').slice(0,50)}</td>
      </tr>`).join('')}
    </tbody></table>`;

  // Posts
  const posts = await fetchJSON('/api/posts');
  document.getElementById('tab-posts').innerHTML = posts.length === 0
    ? '<p style="color:#666">No posts yet.</p>'
    : `<table><thead><tr><th>Time</th><th>Day</th><th>Subreddit</th><th>Title</th><th>Link</th></tr></thead><tbody>
      ${posts.map(p => `<tr>
        <td style="white-space:nowrap">${timeStr(p.posted_at)}</td>
        <td>${p.day_id||'?'}</td>
        <td>r/${p.subreddit||'?'}</td>
        <td>${(p.title||'').slice(0,50)}</td>
        <td>${p.url ? `<a class="url-link" href="${p.url}" target="_blank">open</a>` : '-'}</td>
      </tr>`).join('')}
    </tbody></table>`;

  // Activity Log
  const activity = await fetchJSON('/api/activity-log');
  document.getElementById('tab-activity').innerHTML = activity.length === 0
    ? '<p style="color:#666">No activity log.</p>'
    : `<table><thead><tr><th>Time</th><th>Action</th><th>Subreddit</th><th>Hash</th></tr></thead><tbody>
      ${activity.map(a => `<tr>
        <td style="white-space:nowrap">${timeStr(a.created_at)}</td>
        <td>${tagHTML(a.action_type)}</td>
        <td>r/${a.subreddit||'?'}</td>
        <td style="color:#555">${(a.body_hash||'').slice(0,30)}</td>
      </tr>`).join('')}
    </tbody></table>`;

  // Daily Reports
  const reports = await fetchJSON('/api/daily-reports');
  const karmaHistory = await fetchJSON('/api/karma-history');

  let karmaChart = '';
  if (karmaHistory.length > 1) {
    const maxK = Math.max(...karmaHistory.map(k=>k.karma));
    const minK = Math.min(...karmaHistory.map(k=>k.karma));
    const range = maxK - minK || 1;
    const barH = 80;
    karmaChart = `<div style="display:flex;align-items:flex-end;gap:2px;height:${barH+20}px;margin:10px 0;padding:10px;background:#1a1a1a;border-radius:8px;overflow-x:auto">
      ${karmaHistory.slice().reverse().map(k => {
        const h = Math.max(4, ((k.karma - minK) / range) * barH);
        return `<div title="${k.karma} (${k.recorded_at.slice(0,10)})" style="width:12px;min-width:12px;height:${h}px;background:#ff4500;border-radius:2px"></div>`;
      }).join('')}
    </div><div style="color:#666;font-size:0.75em;text-align:center">Karma History (${karmaHistory.length} records)</div>`;
  }

  document.getElementById('tab-reports').innerHTML = karmaChart + (reports.length === 0
    ? '<p style="color:#666">No daily reports yet.</p>'
    : `<table><thead><tr><th>Date</th><th>Karma</th><th>Change</th><th>Comments</th><th>Posts</th><th>Risk</th><th>Strategy</th></tr></thead><tbody>
      ${reports.map(r => {
        const changeColor = r.karma_change > 0 ? '#4caf50' : r.karma_change < 0 ? '#f44336' : '#666';
        const riskColor = {green:'#4caf50',yellow:'#ffc107',red:'#f44336'}[r.risk_level] || '#666';
        return `<tr>
          <td style="white-space:nowrap">${r.report_date}</td>
          <td style="font-weight:bold;color:#ff4500">${r.karma||'-'}</td>
          <td style="color:${changeColor}">${r.karma_change > 0 ? '+' : ''}${r.karma_change || '0'}</td>
          <td>${r.comments_count}</td>
          <td>${r.posts_count}</td>
          <td><span style="color:${riskColor}">${r.risk_level}</span></td>
          <td style="font-size:0.8em;color:#999;max-width:300px">${(r.strategy_notes||'-').slice(0,100)}</td>
        </tr>`;
      }).join('')}
    </tbody></table>`);

  // Strategy
  const strategies = await fetchJSON('/api/strategies');
  document.getElementById('tab-strategy').innerHTML = strategies.length === 0
    ? '<p style="color:#666">No strategies yet.</p>'
    : `<table><thead><tr><th>Time</th><th>Type</th><th>Subreddit</th><th>Recommendation</th><th>Reason</th><th>Priority</th></tr></thead><tbody>
      ${strategies.map(s => {
        const pColor = s.priority >= 8 ? '#f44336' : s.priority >= 5 ? '#ff9800' : '#4caf50';
        return `<tr>
          <td style="white-space:nowrap">${timeStr(s.created_at)}</td>
          <td>${tagHTML(s.strategy_type)}</td>
          <td>${s.subreddit ? 'r/'+s.subreddit : '-'}</td>
          <td style="color:#ddd">${s.recommendation||''}</td>
          <td style="color:#999;font-size:0.85em">${s.reason||''}</td>
          <td style="color:${pColor};font-weight:bold">${s.priority}</td>
        </tr>`;
      }).join('')}
    </tbody></table>`;

  // Load campaign config + schedule + runner status
  loadCampaignConfig();
  loadSchedule();
  loadRunnerStatus();
}

loadAll();
setInterval(loadRunnerStatus, 5000);
setInterval(loadAll, 30000);
</script>
</body>
</html>"""
