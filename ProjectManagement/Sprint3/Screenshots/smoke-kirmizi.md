# #189 · canlı smoke kanıtı — BİLİNÇLİ KIRMIZI koşum

**Amaç:** smoke'un gerçekten hata YAKALADIĞINI göstermek. Hep yeşil veren bir kontrol hiçbir şey ölçmüyor olabilir; bu koşum kasıtlı yanlış bir web hedefiyle yapıldı.

- **Tarih:** 2026-07-30T12:50:28Z
- **API:** https://api.recommend2me.com
- **Web:** https://example.com
- **Çıkış kodu:** `2`

```
	SMOKE_STRICT="" uv run python scripts/smoke.py
OK   /health github_auth='configured'
OK   /health gemini='configured'
OK   GET https://api.recommend2me.com/health -> 200, status=ok, mode=hosted
FAIL CORS preflight OPTIONS https://api.recommend2me.com/health -> 400 (200/204 bekleniyor)
FAIL CORS GET https://api.recommend2me.com/health -> ACAO='None' != 'https://example.com'
FAIL SPA doğrudan GET https://example.com/ -> 200 ama index.html değil (marker yok)
FAIL SPA refresh GET https://example.com/?_smoke=1785415826 -> 200 ama index.html değil (marker yok)
FAIL SPA doğrudan GET https://example.com/board -> 404
FAIL SPA refresh GET https://example.com/board?_smoke=1785415827 -> 404
FAIL SPA doğrudan GET https://example.com/scope -> 404
FAIL SPA refresh GET https://example.com/scope?_smoke=1785415827 -> 404
FAIL SPA doğrudan GET https://example.com/graph -> 404
FAIL SPA refresh GET https://example.com/graph?_smoke=1785415827 -> 404
FAIL SPA doğrudan GET https://example.com/activity -> 404
FAIL SPA refresh GET https://example.com/activity?_smoke=1785415828 -> 404
FAIL SPA doğrudan GET https://example.com/ask -> 404
FAIL SPA refresh GET https://example.com/ask?_smoke=1785415828 -> 404
SMOKE KIRMIZI — 14 hata, 0 uyarı
make: *** [smoke] Error 1
```
