# team_ranking_back_alt.py
from __future__ import annotations

import os
from datetime import datetime, timedelta
from io import BytesIO

from flask import Flask, render_template, request, send_file, jsonify, redirect
import requests

from team_ranking_alt import fetch_team_rankings  # ← 파일명 변경 반영

app = Flask(__name__, template_folder="templates")

# ---- 간단 캐시 (콜드스타트/타임아웃 완화) ----
CACHE_TTL_MIN = int(os.environ.get("CACHE_TTL_MIN", "10"))
_cache_data = {"rankings": [], "updated_at": None}  # type: ignore[assignment]

def _cache_stale() -> bool:
    ts = _cache_data["updated_at"]
    if ts is None:
        return True
    return datetime.now() - ts > timedelta(minutes=CACHE_TTL_MIN)

def _get_rankings():
    if _cache_stale():
        try:
            data = fetch_team_rankings()
            if data:
                _cache_data["rankings"] = data
                _cache_data["updated_at"] = datetime.now()
        except Exception as e:
            # 최초 실패 시에도 이전 캐시 유지
            print("[fetch_team_rankings] error:", e)
    return _cache_data["rankings"]

# ---- 라우트 ----
@app.route("/")
def root():
    # 루트로 들어오면 팀순위 페이지로 리다이렉트
    return redirect("/team-ranking")

@app.route("/healthz")
def healthz():
    return "ok", 200

@app.route("/team-ranking")
def show_ranking():
    rankings = _get_rankings()
    # 선택 하이라이트가 필요한 템플릿이라면 아래 라인도 함께 넘겨 사용 가능
    selected_team = request.args.get("team", "")
    return render_template("team_ranking_alt.html", rankings=rankings, selected_team=selected_team)

@app.route("/team-ranking.json")
def show_ranking_json():
    return jsonify({
        "updated_at": _cache_data["updated_at"].isoformat() if _cache_data["updated_at"] else None,
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
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
            ),
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
