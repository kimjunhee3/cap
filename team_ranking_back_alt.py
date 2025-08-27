# team_ranking_back_alt.py
from __future__ import annotations

import os
from datetime import datetime, timedelta
from io import BytesIO

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
from shorts_back_alt import shorts_bp  # ✅ 숏츠 블루프린트 등록

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.register_blueprint(shorts_bp)  # ✅ /shorts, /shorts/ping 활성화

# -----------------------------
# CORS 설정
# -----------------------------
# 기본은 모두 허용("*"). 운영에서는 환경변수로 Netlify 도메인만 허용 권장:
#   CORS_ALLOW_ORIGIN="https://your-site.netlify.app"
ALLOWED_ORIGIN = os.environ.get("CORS_ALLOW_ORIGIN", "*")


@app.after_request
def add_cors_headers(resp):
    """모든 응답에 CORS 헤더 부착 (fetch 사용 시 브라우저 차단 방지)"""
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Vary"] = "Origin"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    # 필요 시 인증 쿠키 사용:
    # resp.headers["Access-Control-Allow-Credentials"] = "true"
    return resp


@app.route("/<path:any_path>", methods=["OPTIONS"])
def cors_preflight(any_path):
    """모든 경로에 대해 OPTIONS 프리플라이트 응답"""
    r = make_response("", 204)
    r.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    r.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return r


# -----------------------------
# 간단 캐시
# -----------------------------
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


# -----------------------------
# 라우트
# -----------------------------
@app.route("/")
def home():
    # ✅ 대시보드(팀순위 + 숏츠) 페이지 렌더
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
    """
    팀 순위 HTML. App.js(넷리파이)에서
    https://.../team-ranking?team=<slug>&auto_select=1&embed=1
    로 임베드합니다.
    """
    rankings = _get_rankings()
    selected_team = request.args.get("team", "")
    try:
        # ✅ 템플릿 파일명: team_ranking_alt.html
        return render_template(
            "team_ranking_alt.html",
            rankings=rankings,
            selected_team=selected_team,
        )
    except TemplateNotFound:
        # 폴백 테이블 (템플릿 미존재시)
        if not rankings:
            return "<div>팀 순위 데이터가 아직 없습니다. 잠시 후 새로고침 해주세요.</div>", 200
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
    """프론트에서 직접 fetch 하고 싶을 때 쓰는 JSON 엔드포인트"""
    return jsonify(
        {
            "updated_at": _cache["ts"].isoformat() if _cache["ts"] else None,
            "rankings": _get_rankings(),
        }
    )


@app.route("/proxy-logo")
def proxy_logo():
    """
    로고 이미지를 프락시. (네이버 리퍼러/UA 요구 대응)
    템플릿에서는 /proxy-logo?url=<encoded> 로 사용.
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
