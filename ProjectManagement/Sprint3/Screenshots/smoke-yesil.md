# #189 · canlı smoke kanıtı — YEŞİL koşum

Production hedefine karşı gerçek koşum. 6 SPA route × (doğrudan + refresh) + CORS preflight + `/health` readiness.

- **Tarih:** 2026-07-30T12:50:25Z
- **API:** https://api.recommend2me.com
- **Web:** https://recommend2me.com
- **Çıkış kodu:** `0`

```
	SMOKE_STRICT="" uv run python scripts/smoke.py
OK   /health github_auth='configured'
OK   /health gemini='configured'
OK   GET https://api.recommend2me.com/health -> 200, status=ok, mode=hosted
OK   CORS preflight OPTIONS https://api.recommend2me.com/health -> 200, ACAO='https://recommend2me.com'
OK   CORS GET https://api.recommend2me.com/health -> ACAO='https://recommend2me.com'
OK   SPA doğrudan GET https://recommend2me.com/ -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/?_smoke=1785415823 -> 200 + marker
OK   SPA doğrudan GET https://recommend2me.com/board -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/board?_smoke=1785415824 -> 200 + marker
OK   SPA doğrudan GET https://recommend2me.com/scope -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/scope?_smoke=1785415824 -> 200 + marker
OK   SPA doğrudan GET https://recommend2me.com/graph -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/graph?_smoke=1785415824 -> 200 + marker
OK   SPA doğrudan GET https://recommend2me.com/activity -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/activity?_smoke=1785415825 -> 200 + marker
OK   SPA doğrudan GET https://recommend2me.com/ask -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/ask?_smoke=1785415825 -> 200 + marker
SMOKE YEŞİL
```
