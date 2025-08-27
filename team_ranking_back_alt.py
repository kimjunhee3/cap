# team_ranking_back_alt.py
from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional, List, Dict

from flask import (
    Flask,
    render_template,
    request,
    send_file,
    jsonify,
    make_response,
)
from jinja2 import TemplateNotFound
import requests

from team_ranking_alt import fetch_team_rankings
from shorts_back_alt import shorts_bp  # ✅ /shorts 블루프린트

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.register_blueprint(shorts_bp)

# -----------------------------
# CORS (프론트에서 fetch 할 때 에러 방지)
# -----------------------------
ALLOWED_ORIGIN = os.environ.get("CORS_ALLOW_ORIGIN", "*")

@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Vary"] = "Origin"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

@app.route("/<path:any_path>", methods=["OPTIONS"])
def cors_preflight(any_path):
    r = make_response("", 204)
    r.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    r.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return r

@app.route("/favicon.ico")
def favicon():
    # 파비콘 없을 때 405/404 뜨는 것 방지
    return ("", 204)

# -----------------------------
# 캐시 (논블로킹 리프레시)
# -----------------------------
CACHE_TTL_MIN = int(os.environ.get("CACHE_TTL_MIN", "10"))

_cache: dict = {"rankings": [], "ts": None}
_fetch_lock = threading.Lock()
_is_refreshing = False  # 동시 갱신 방지

def _stale() -> bool:
    ts: Optional[datetime] = _cache["ts"]
    if ts is None:
        return True
    return datetime.now() - ts > timedelta(minutes=CACHE_TTL_MIN)

def _refresh_cache_background():
    """Selenium 크롤링을 백그라운드에서 실행 (요청 블로킹 방지)"""
    global _is_refreshing
    with _fetch_lock:
        if _is_refreshing:
            return
        _is_refreshing = True
    try:
        app.logger.info("[ranking] background refresh start")
        data = fetch_team_rankings()
        if data:
            _cache["rankings"] = data
            _cache["ts"] = datetime.now()
            app.logger.info("[ranking] background refresh done: %d rows", len(data))
        else:
            app.logger.warning("[ranking] background refresh returned empty list")
    except Exception as e:
        app.logger.exception("[ranking] background refresh error: %s", e)
    finally:
        _is_refreshing = False

def _get_rankings_nonblocking() -> List[Dict]:
    """
    - 캐시가 신선하면 즉시 반환
    - 오래됐으면 백그라운드로 갱신 트리거 후, 현재 캐시(비어 있을 수도 있음) 반환
    """
    if _stale():
        threading.Thread(target=_refresh_cache_background, daemon=True).start()
    return _cache["rankings"]

# 서버 기동 시 1회 미리 가져오기(비동기)
threading.Thread(target=_refresh_cache_background, daemon=True).start()

# -----------------------------
# 라우트
# -----------------------------
@app.route("/")
def home():
    try:
        return render_template("combined.html")
    except TemplateNotFound:
        return '<p><a href="/team-ranking">팀 순위</a> · <a href="/shorts">숏츠</a></p>', 200

@app.route("/healthz")
def healthz():
    return "ok", 200

@app.route("/team-ranking")
def show_ranking():
    """
    - 단독 접근: /team-ranking
    - 임베드: /team-ranking?team=<slug>&auto_select=1&embed=1
    """
    rankings = _get_rankings_nonblocking()
    selected_team = request.args.get("team", "")
    try:
        return render_template(
            "team_ranking_alt.html",
            rankings=rankings,
            selected_team=selected_team,
        )
    except TemplateNotFound:
        # 폴백(템플릿이 없을 때)
        if not rankings:
            return "<div>팀 순위 데이터 준비 중입니다. 잠시 후 새로고침 해주세요.</div>", 200
        cols = ["rank", "team_name", "wins", "losses", "draws", "gb"]
        head = "".join(f"<th>{c}</th>" for c in cols)
        body = "".join(
            "<tr>" + "".join(f"<td>{r.get(c,'')}</td>" for c in cols) + "</tr>"
            for r in rankings
        )
        return (
            f"<h3>팀 순위</h3>"
            f"<table border='1' cellpadding='6' cellspacing='0'>"
            f"<thead><tr>{head}</tr></thead>"
            f"<tbody>{body}</tbody></table>",
            200,
        )

@app.route("/team-ranking.json")
def show_ranking_json():
    return jsonify(
        {
            "updated_at": _cache["ts"].isoformat() if _cache["ts"] else None,
            "rankings": _get_rankings_nonblocking(),
        }
    )

@app.route("/proxy-logo")
def proxy_logo():
    """
    네이버 이미지 리퍼러/UA 요구 대응 프록시
    사용법: /proxy-logo?url=<encoded>
    """
    url = request.args.get("url")
    if not url:
        return "Missing URL", 400
    try:
        headers = {
            "Referer": "https://sports.naver.com",
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/15.0 Mobile/15E148 Safari/604.1"
            ),
        }
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return f"Image fetch failed with status {r.status_code}", 502
        mimetype = r.headers.get("Content-Type", "image/png")
        return send_file(BytesIO(r.content), mimetype=mimetype)
    except Exception as e:
        return f"Error fetching image: {str(e)}", 500

# -----------------------------
# 실행
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
