# 🛡️ Master Monitor

نظام مراقبة تلقائي لكل مواقعك.

## الملفات

| الملف | الوظيفة |
|---|---|
| `config.yaml` | إعدادات المواقع |
| `monitor.py` | script الفحص |
| `.github/workflows/monitor.yml` | يشتغل كل 30 دقيقة |
| `dashboard/index.html` | Dashboard |

## إعداد Secrets في GitHub

روحي: repo → Settings → Secrets → Actions → New secret

| Secret | القيمة |
|---|---|
| `TELEGRAM_TOKEN` | token بوت التليجرام |
| `TELEGRAM_CHAT_ID` | الـ chat ID بتاعك |
| `MONITOR_GITHUB_TOKEN` | GitHub token بصلاحيات repo |

## إضافة موقع جديد

في `config.yaml` أضيفي:

```yaml
  - name: NewSite
    url: https://newsite.com
    github_repo: username/repo
    pages:
      - /
```

## تشغيل محلي

```bash
pip install requests pyyaml
python monitor.py
```
