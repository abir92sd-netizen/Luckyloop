import requests
import time
import threading
import os
from bs4 import BeautifulSoup
from datetime import datetime

SERVER_URL = "https://luckyloop-position-update-16-05-gmd8.onrender.com"
PHPSESSID  = os.environ.get("MW_PHPSESSID", "1pueldedsne9qu2d7fmf6decej")

JOB_NAMES = [
    {"full": "TTV-Data Entry - PC required. Not for mobile phones. (E766-1470)", "short": "1470"},
    {"full": "TTV-Data Entry from images (E502-1033)",                            "short": "1033"},
    {"full": "TTV-Data Entry from images (E1096-1891)",                           "short": "1891"},
    {"full": "TTV-Data Entry from images (E833-1532)",                            "short": "1532"},
    {"full": "TTV-Data Entry - PC required. Not for mobile phones. (E766-2289)",  "short": "2289"},
    {"full": "TTV-Data Entry (E766-1469sv)",                                      "short": "1469"},
    {"full": "TTV-Data Entry from images (E502-1001)",                            "short": "1001"},
]

TARGET_URL = "https://www.microworkers.com/jobs.php?Filter=no&Sort=NEWEST&Id_category=09"
EMPLOYER_URL = "https://www.microworkers.com/userinfo.php?Id=4b256e28"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Cookie": f"PHPSESSID={PHPSESSID}"
})

def calc_available(pos_str):
    try:
        cur, total = pos_str.split("/")
        return str(max(int(total) - int(cur), 0))
    except:
        return "-"

def update_status(status, message):
    try:
        requests.post(f"{SERVER_URL}/api/scraper-status", json={
            "status" : status,
            "message": message
        }, timeout=10)
        print(f"[Status] {status} | {message}")
    except Exception as e:
        print(f"[Status Error] {e}")

def scrape_jobs():
    try:
        r = session.get(TARGET_URL, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        listings = soup.select(".jobslist")
        count = len(listings)
        print(f"[Scraper] Found {count} listings")

        if count == 0:
            update_status("expired", "⚠️ PHPSESSID Expired! Render এ নতুন Cookie দিন।")
            return

        update_status("ok", f"✅ Running | {count} listings found")

        for job in JOB_NAMES:
            for item in listings:
                name_el = item.select_one(".jobname a")
                pos_el  = item.select_one(".jobdone p")
                if not name_el or not pos_el:
                    continue
                if name_el.get_text(strip=True) == job["full"]:
                    position  = pos_el.get_text(strip=True)
                    available = calc_available(position)
                    link      = name_el.get("href", TARGET_URL)
                    push(job["short"], position, available, link)
                    break

    except Exception as e:
        print(f"[Scraper] Error: {e}")
        update_status("error", f"❌ Error: {str(e)[:80]}")

def push(cid, position, available, link):
    try:
        requests.post(f"{SERVER_URL}/save", json={
            "job_name" : cid,
            "position" : position,
            "available": available,
            "link"     : link
        }, timeout=10)
        print(f"[Scraper] Pushed {cid} pos={position} avail={available}")
    except Exception as e:
        print(f"[Scraper] Push error: {e}")

# ══════════════════════════════════════════════════════
# TASKS PAID TRACKER — প্রতি ১ মিনিটে scrape করবে
# ══════════════════════════════════════════════════════

def scrape_tasks_paid():
    """microworkers.com/userinfo.php?Id=4b256e28 থেকে Tasks paid নাও"""
    try:
        r = session.get(EMPLOYER_URL, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        # "Tasks paid" row খুঁজো — HG Campaigns section এ
        tasks_paid = None
        rows = soup.select("table tr")
        for row in rows:
            cells = row.find_all(["th", "td"])
            for i, cell in enumerate(cells):
                if "Tasks paid" in cell.get_text():
                    # পরের cell এ number আছে
                    if i + 1 < len(cells):
                        val = cells[i + 1].get_text(strip=True).replace(",", "").replace(".", "")
                        if val.isdigit():
                            tasks_paid = int(val)
                            break
            if tasks_paid is not None:
                break

        # Alternative: সব text থেকে খোঁজো
        if tasks_paid is None:
            text = soup.get_text()
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if "Tasks paid" in line:
                    # পরের non-empty line এ number থাকতে পারে
                    for j in range(i+1, min(i+5, len(lines))):
                        val = lines[j].strip().replace(",", "").replace(".", "")
                        if val.isdigit() and len(val) > 4:
                            tasks_paid = int(val)
                            break
                    if tasks_paid:
                        break

        if tasks_paid is None:
            print("[TasksPaid] Could not find Tasks paid value")
            return

        print(f"[TasksPaid] Current: {tasks_paid:,}")

        # Server এ push করো
        try:
            requests.post(f"{SERVER_URL}/api/tasks-paid", json={
                "tasks_paid": tasks_paid
            }, timeout=10)
            print(f"[TasksPaid] Pushed: {tasks_paid:,}")
        except Exception as e:
            print(f"[TasksPaid] Push error: {e}")

    except Exception as e:
        print(f"[TasksPaid] Scrape error: {e}")


def scrape_loop():
    print("[Scraper] Starting — checking at sec 2, 4, 33...")
    time.sleep(5)
    CHECK_SECONDS = {2, 4, 33}
    last_checked_sec = -1

    # Tasks paid — আলাদা counter
    last_tasks_paid_check = 0

    while True:
        now = datetime.now()
        sec = now.second

        # Jobs scrape — sec 2, 4, 33 এ
        if sec in CHECK_SECONDS and sec != last_checked_sec:
            last_checked_sec = sec
            print(f"[Scraper] Checking at :{sec:02d}")
            scrape_jobs()

        # Tasks paid — প্রতি ৬০ সেকেন্ডে
        current_time = time.time()
        if current_time - last_tasks_paid_check >= 60:
            last_tasks_paid_check = current_time
            print(f"[TasksPaid] Checking at {now.strftime('%H:%M:%S')}")
            scrape_tasks_paid()

        time.sleep(0.5)

def start_scraper():
    t = threading.Thread(target=scrape_loop, daemon=True)
    t.start()
