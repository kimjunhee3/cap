# team_ranking_back_alt.py
from __future__ import annotations

import os
from datetime import datetime, timedelta
from io import BytesIO

from flask import Flask, render_template, request, send_file, jsonify
from jinja2 import TemplateNotFound
import requests

from team_ranking_alt import fetch_team_rankings
from shorts_back_alt import shorts_bp  # ✅ 숏츠 블루프린트 등록

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.register_blueprint(shorts_bp)  # ✅ /shorts, /shorts/ping 활성화

# ---- 간단 캐시 ----
CACHE_TTL_MIN = int(os.environ.get("CACHE_TTL_MIN", "10"))
_cache = {"rankings": [], "ts": None}

def _stale() -> bool:
    ts = _cache["ts"]
    if ts is None:
        return True
    return datetime.now() - ts > timedelta(minutes=CACHE_TTL_MIN)

def _get_rankings():
    if _stale():
        try:
            data = fetch_team_rankings()
            if data:
                _cache["rankings"] = data
                _cache["ts"] = datetime.now()
        except Exception as e:
            print("[fetch_team_rankings] error:", e)
    return _cache["rankings"]

# ---- 라우트 ----
@app.route("/")
def home():
    # ✅ 이제는 대시보드(팀순위 + 숏츠) 페이지를 렌더
    try:
        return render_template("combined.html")
    except TemplateNotFound:
        # 템플릿이 없을 때 간단 링크 폴백
        return '<p><a href="/team-ranking">팀 순위</a> · <a href="/shorts">숏츠</a></p>', 200

@app.route("/healthz")
def healthz():
    return "ok", 200

@app.route("/team-ranking")
def show_ranking():
    rankings = _get_rankings()
    selected_team = request.args.get("team", "")
    try:
        # ✅ 현재 템플릿 파일명이 team_ranking_alt.html 이므로 그걸로 렌더
        return render_template("team_ranking_alt.html", rankings=rankings, selected_team=selected_team)
    except TemplateNotFound:
        # 폴백 테이블
        if not rankings:
            return "<div>팀 순위 데이터가 아직 없습니다. 잠시 후 새로고침 해주세요.</div>", 200
        cols = ["rank","team_name","wins","losses","draws","gb"]
        head = "".join(f"<th>{c}</th>" for c in cols)
        body = "".join(
            "<tr>" + "".join(f"<td>{r.get(c,'')}</td>" for c in cols) + "</tr>"
            for r in rankings
        )
        return f"<h3>팀 순위</h3><table border='1' cellpadding='6' cellspacing='0'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>", 200

@app.route("/team-ranking.json")
def show_ranking_json():
    return jsonify({
        "updated_at": _cache["ts"].isoformat() if _cache["ts"] else None,
        "rankings": _get_rankings()
    })

@app.route("/proxy-logo")
def proxy_logo():
    url = request.args.get("url")
    if not url:
        return "Missing URL", 400
    try:
        headers = {
            "Referer": "https://sports.naver.com",
            "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
                           "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1")
        }
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return f"Image fetch failed with status {r.status_code}", 502
        mimetype = r.headers.get("Content-Type", "image/png")
        return send_file(BytesIO(r.content), mimetype=mimetype)
    except Exception as e:
        return f"Error fetching image: {str(e)}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
