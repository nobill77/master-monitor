import os
import json
import yaml
import requests
import ssl
import socket
from datetime import datetime, timezone
from pathlib import Path

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

RESULTS_FILE = Path("dashboard/results.json")


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def check_url(url, timeout=10):
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        return r.status_code, None
    except requests.exceptions.ConnectionError as e:
        return None, f"Connection error: {str(e)[:80]}"
    except requests.exceptions.Timeout:
        return None, "Timeout"
    except Exception as e:
        return None, str(e)[:80]


def check_ssl(url):
    try:
        hostname = url.replace("https://", "").replace("http://", "").split("/")[0]
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
            s.settimeout(10)
            s.connect((hostname, 443))
            cert = s.getpeercert()
            expire_str = cert["notAfter"]
            expire_dt = datetime.strptime(expire_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            days_left = (expire_dt - datetime.now(timezone.utc)).days
            return days_left, None
    except Exception as e:
        return None, str(e)[:80]


def check_github_actions(repo, token):
    if not token:
        return None, "No GitHub token"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=1"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None, f"GitHub API error: {r.status_code}"
        runs = r.json().get("workflow_runs", [])
        if not runs:
            return "no_runs", None
        last = runs[0]
        return last["conclusion"], None
    except Exception as e:
        return None, str(e)[:80]


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram not configured — skipping alert")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")


def run_checks():
    config = load_config()
    now = datetime.now(timezone.utc).isoformat()
    results = {"checked_at": now, "sites": []}
    alerts = []

    for site in config["sites"]:
        name = site["name"]
        base_url = site["url"].rstrip("/")
        repo = site.get("github_repo", "")
        pages = site.get("pages", ["/"])

        print(f"\n🔍 Checking {name} ({base_url})")
        site_result = {"name": name, "url": base_url, "checked_at": now, "pages": [], "ssl_days": None, "github_status": None, "overall": "ok"}
        site_issues = []

        # Check pages
        for page in pages:
            url = base_url + page
            status, error = check_url(url, config["settings"].get("timeout_seconds", 10))
            ok = status == 200
            site_result["pages"].append({"path": page, "status": status, "ok": ok, "error": error})
            print(f"  {'✅' if ok else '❌'} {page} → {status or error}")
            if not ok:
                site_issues.append(f"❌ {page} → {status or error}")

        # Check SSL
        if base_url.startswith("https"):
            days, err = check_ssl(base_url)
            site_result["ssl_days"] = days
            print(f"  {'✅' if days and days > 14 else '⚠️'} SSL: {days} days left" if days else f"  ⚠️ SSL check failed: {err}")
            if days and days < 14:
                site_issues.append(f"⚠️ SSL expires in {days} days")

        # Check GitHub Actions
        if repo:
            conclusion, err = check_github_actions(repo, GITHUB_TOKEN)
            site_result["github_status"] = conclusion
            ok_gh = conclusion in ("success", "no_runs", None)
            print(f"  {'✅' if ok_gh else '❌'} GitHub Actions: {conclusion or err}")
            if conclusion and conclusion not in ("success", "no_runs") and conclusion is not None:
                site_issues.append(f"❌ GitHub Actions: {conclusion}")

        if site_issues:
            site_result["overall"] = "down"
            alert_msg = f"🚨 <b>{name} — ISSUES DETECTED</b>\n"
            alert_msg += f"🕐 {now[:16].replace('T', ' ')} UTC\n\n"
            alert_msg += "\n".join(site_issues)
            alerts.append(alert_msg)

        results["sites"].append(site_result)

    # Save results
    RESULTS_FILE.parent.mkdir(exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Results saved to {RESULTS_FILE}")

    # Send alerts
    for alert in alerts:
        print(f"\n📨 Sending alert:\n{alert}")
        send_telegram(alert)

    all_ok = all(s["overall"] == "ok" for s in results["sites"])
    print(f"\n{'✅ All sites OK!' if all_ok else '🚨 Issues found!'}")
    return results


if __name__ == "__main__":
    run_checks()
