# 🛡️ Master Monitor — the outside watcher

Watches the Lair server **from outside** (GitHub Actions), so a dead or suspended server, or a stopped monitor, is
noticed even when nothing on the server can report it. Rebuilt 24 Sep 2026.

| What | How |
|---|---|
| Server down / suspended / unreachable | the heartbeat `https://www.lexplair.com/__lair/heartbeat.json` (and trendlair's) does not answer |
| Server's monitor stopped | the heartbeat is older than 20 minutes |
| Server can no longer e-mail | the heartbeat says `mail_ok: false` |
| Daily record missing | `digest_last` older than 27 hours |
| Pages and edge TLS | as before (Cloudflare may serve cached pages while the server is down — hence the heartbeat) |

**Alerts:** an issue in this repository per problem, @mentioning the owner (GitHub e-mails it from its own servers and
shows it in the GitHub app); it closes itself on recovery. Optional push: repository secret `NTFY_TOPIC`.

**Staged test:** Actions → Master Monitor → Run workflow → simulate = `down` or `stale`.
