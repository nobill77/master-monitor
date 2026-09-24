"""Master Monitor — the OUTSIDE watcher of the Lair server (rebuilt 2026-09-24).

Runs on GitHub Actions, i.e. somewhere that shares nothing with the server: not its network, not its e-mail (Resend),
not its power. It answers one question the server cannot answer about itself: is the server, and its own monitor,
alive?

  * Heartbeat: https://www.lexplair.com/__lair/heartbeat.json (and the same on trendlair) is written by the server's
    monitor on every 5-minute run and is never cached by Cloudflare. Unreachable on both hosts -> SERVER DOWN (or
    suspended, or its DNS/Cloudflare path broken). Reachable but older than STALE_MIN -> the MONITOR stopped.
  * The heartbeat also says whether the server can still send e-mail and when its daily record last went out; if the
    server's own alerting is broken, this watcher raises the alarm instead.
  * Public pages and edge TLS are still checked (note: Cloudflare may serve cached pages while the origin is down —
    that is exactly why the heartbeat exists).

Alerts: a GitHub issue per problem in this repository, @mentioning the owner (GitHub notifies by e-mail from its own
servers and in the GitHub app), kept open while the problem lasts and closed with a comment when it recovers.
Optional push: if the repository secret NTFY_TOPIC is set, the same line is pushed to the owner's phone (ntfy).
"""
import json
import os
import socket
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

REPO = os.environ.get('GITHUB_REPOSITORY', 'nobill77/master-monitor')
TOKEN = os.environ.get('GITHUB_TOKEN', '')
NTFY_TOPIC = os.environ.get('NTFY_TOPIC', '')
OWNER = os.environ.get('OWNER_HANDLE', 'nobill77')
RESULTS = Path('dashboard/results.json')
LABEL = 'lair-alert'


def load_config():
    return yaml.safe_load(open('config.yaml', encoding='utf-8'))


def get(url, timeout=15):
    try:
        r = requests.get(url, timeout=timeout, headers={'User-Agent': 'lair-master-monitor/2', 'Cache-Control': 'no-cache'})
        return r.status_code, r
    except requests.RequestException as e:
        return None, f'{type(e).__name__}: {str(e)[:120]}'


def ssl_days(host):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as s, ctx.wrap_socket(s, server_hostname=host) as t:
            na = t.getpeercert()['notAfter']
        return (datetime.strptime(na, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
    except Exception:
        return None


def check_heartbeat(cfg, sim=None):
    """-> list of (key, message) problems, and the heartbeat seen."""
    hb, errors = None, []
    for url in cfg['heartbeat']['urls']:
        st, r = get(url + f'?t={int(time.time())}')
        if st == 200:
            try:
                hb = r.json(); break
            except ValueError:
                errors.append(f'{url}: not JSON')
        else:
            errors.append(f'{url}: {st if st else r}')
    if sim == 'down':
        hb, errors = None, ['simulated: both heartbeat URLs unreachable']
    if sim == 'stale' and hb:
        hb['epoch'] -= 3600
    problems = []
    if hb is None:
        problems.append(('server-down', 'SERVER DOWN or unreachable: the heartbeat does not answer on either site — '
                         + '; '.join(errors) + '. Possible causes: server stopped or suspended (billing), network, '
                         'Cloudflare/DNS path. Check the Hetzner console first.'))
        return problems, None
    age_min = (time.time() - hb['epoch']) / 60
    if age_min > cfg['heartbeat']['stale_min']:
        problems.append(('monitor-stopped', f"MONITOR STOPPED: the server answers but its monitor last ran {age_min:.0f} minutes "
                         f"ago ({hb.get('ts')}). The sites may be fine, but nothing is being checked or repaired. "
                         "On the server: systemctl status lair-monitor.timer lair-monitor.service"))
    if hb.get('mail_ok') is False:
        problems.append(('server-mail', f"The server can no longer send e-mail (last attempt {hb.get('mail_last')}): its own alerts "
                         "and daily record are not reaching you. Check the Resend key/account."))
    dl = hb.get('digest_last')
    if dl:
        age_h = (datetime.now(timezone.utc) - datetime.strptime(dl, '%Y-%m-%d %H:%M UTC').replace(tzinfo=timezone.utc)).total_seconds() / 3600
        if age_h > 27:
            problems.append(('no-digest', f"The server's daily record has not been produced for {age_h:.0f} hours."))
    if hb.get('failing_critical') and hb.get('mail_ok') is False:
        problems.append(('critical-unreported', 'Critical checks failing on the server while it cannot e-mail: '
                         + ', '.join(hb['failing_critical'])))
    return problems, hb


def check_sites(cfg):
    problems, out = [], []
    for site in cfg['sites']:
        base = site['url'].rstrip('/')
        for page in site.get('pages', ['/']):
            st, r = get(base + page, cfg['settings'].get('timeout_seconds', 15))
            out.append({'site': site['name'], 'path': page, 'status': st if st else str(r)})
            if st != 200:
                problems.append((f"page-{site['name']}-{page}", f"{site['name']} {page} answered {st if st else r}"))
        host = base.split('//', 1)[1].split('/')[0]
        d = ssl_days(host)
        out.append({'site': site['name'], 'ssl_days': d})
        if d is not None and d < cfg['settings'].get('ssl_warn_days', 14):
            problems.append((f"ssl-{site['name']}", f"{site['name']}: edge TLS certificate expires in {d} days"))
    return problems, out


# ---- alerts: GitHub issues (+ optional ntfy) ----------------------------------------------------------------------
def gh(method, path, **kw):
    return requests.request(method, f'https://api.github.com/repos/{REPO}{path}', timeout=20,
                            headers={'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/vnd.github+json'}, **kw)


def open_issues():
    r = gh('GET', f'/issues?state=open&labels={LABEL}&per_page=100')
    return {i['title'].split('] ', 1)[0].lstrip('['): i for i in r.json()} if r.ok else {}


def push(msg, prio=5):
    if NTFY_TOPIC:
        try:
            requests.post(f'https://ntfy.sh/{NTFY_TOPIC}', data=msg[:300].encode(), timeout=10,
                          headers={'Title': 'Lair outside watcher', 'Priority': str(prio)})
        except requests.RequestException:
            pass


def alert(problems):
    if not TOKEN:
        print('no token: alerts not sent'); return
    existing = open_issues()
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    keys = {k for k, _ in problems}
    for k, msg in problems:
        if k in existing:
            continue                                   # already open: GitHub already told the owner
        body = f"@{OWNER} {msg}\n\nDetected by the outside watcher at {now}. This issue closes itself when it recovers."
        r = gh('POST', '/issues', json={'title': f'[{k}] {msg[:90]}', 'body': body, 'labels': [LABEL]})
        print('issue opened' if r.ok else f'issue failed {r.status_code} {r.text[:200]}', k)
        push(f'{msg[:250]}')
    for k, issue in existing.items():
        if k not in keys:
            gh('POST', f"/issues/{issue['number']}/comments", json={'body': f'Recovered at {now}.'})
            gh('PATCH', f"/issues/{issue['number']}", json={'state': 'closed'})
            print('issue closed', k)
            push(f'RECOVERED: {k}', 3)


def main():
    cfg = load_config()
    sim = os.environ.get('SIMULATE') or None
    hb_problems, hb = check_heartbeat(cfg, sim)
    site_problems, pages = check_sites(cfg)
    problems = hb_problems + site_problems
    for k, m in problems:
        print('PROBLEM', k, m)
    if sim:
        problems = [(f'test-{k}', f'[staged test, SIMULATE={sim}] {m}') for k, m in problems]
    alert(problems)
    RESULTS.parent.mkdir(exist_ok=True)
    json.dump({'checked_at': datetime.now(timezone.utc).isoformat(), 'heartbeat': hb, 'pages': pages,
               'problems': [{'key': k, 'message': m} for k, m in problems]}, open(RESULTS, 'w'), indent=2)
    print('OK' if not problems else f'{len(problems)} problem(s)')


if __name__ == '__main__':
    main()
