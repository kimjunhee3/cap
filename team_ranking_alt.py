# team_ranking_alt.py
from __future__ import annotations

import os
import platform
from typing import List, Dict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


def _make_driver() -> webdriver.Chrome:
    """
    Windows(로컬)는 시스템 Chrome, Linux/Docker(Railway)는
    CHROME_BIN / CHROMEDRIVER_BIN 환경변수 경로를 사용합니다.
    """
    opts = Options()
    # 안정 플래그
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,1024")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
    )

    if platform.system() == "Windows":
        # 로컬 윈도우: 설치된 Chrome 사용
        return webdriver.Chrome(options=opts)

    # Linux/Railway: Dockerfile/Nixpacks에서 설치된 바이너리 경로 사용
    opts.binary_location = os.getenv("CHROME_BIN", "/usr/bin/chromium")
    service = Service(os.getenv("CHROMEDRIVER_BIN", "/usr/bin/chromedriver"))
    return webdriver.Chrome(service=service, options=opts)


def fetch_team_rankings() -> List[Dict[str, str]]:
    driver = _make_driver()
    url = "https://m.sports.naver.com/kbaseball/record/index"
    driver.get(url)

    try:
        WebDriverWait(driver, 40).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ol.TableBody_list__P8yRn"))
        )
    except Exception:
        # 디버깅에 도움
        try:
            with open("debug.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        except Exception:
            pass
        driver.quit()
        raise

    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    table = soup.select_one("ol.TableBody_list__P8yRn")
    if not table:
        return []

    team_list = table.select("li.TableBody_item__eCenH")
    data: List[Dict[str, str]] = []

    for team in team_list:
        cells = team.select("div.TableBody_cell__rFrpm")
        if len(cells) < 6:
            continue

        team_info = cells[0]
        team_name_el = team_info.select_one(".TeamInfo_team_name__dni7F")
        rank_el = team_info.select_one(".TeamInfo_ranking__MqHpq")
        logo_img = team_info.select_one(".TeamInfo_emblem__5JUAY img")
        logo_url = logo_img["src"] if logo_img and logo_img.has_attr("src") else ""

        def get_stat(cell) -> str:
            blind = cell.select_one("span.blind")
            if blind and blind.next_sibling:
                return str(blind.next_sibling).strip()
            return cell.get_text(strip=True)

        team_name = team_name_el.get_text(strip=True) if team_name_el else ""
        rank = (rank_el.get_text(strip=True) if rank_el else "").replace("위", "")

        gb = get_stat(cells[2])
        wins = get_stat(cells[3])
        draws = get_stat(cells[4])
        losses = get_stat(cells[5])

        data.append(
            {
                "rank": rank,
                "team_name": team_name,
                "logo": logo_url,
                "gb": gb,
                "wins": wins,
                "draws": draws,
                "losses": losses,
            }
        )

    return data


if __name__ == "__main__":
    for row in fetch_team_rankings():
        print(row)
