# #189 canlı smoke — CP1252 (Windows varsayılan konsol) regresyon kanıtı
# Tarih: 2026-07-27 · Hedefler: api.recommend2me.com + recommend2me.com
# Ortam: PYTHONIOENCODING=cp1252:strict  (Semih'in Windows koşumunun taklidi)

## 1) ÖNCESİ — düzeltmesiz sürüm: exit 1, SPA kontrollerine HİÇ ULAŞAMIYOR
```
  File "/Users/fatiherencetin/.claude/jobs/c8531281/tmp/smoke_eski.py", line 497, in main
    print(line)
  File "/Users/fatiherencetin/.local/share/uv/python/cpython-3.12.12-macos-aarch64-none/lib/python3.12/encodings/cp1252.py", line 19, in encode
    return codecs.charmap_encode(input,self.errors,encoding_table)[0]
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
UnicodeEncodeError: 'charmap' codec can't encode character '\u011f' in position 11: character maps to <undefined>
```

## 2) SONRASI — aynı ortam, aynı komut: exit 0
```
OK   /health github_auth='configured'
OK   /health gemini='configured'
OK   GET https://api.recommend2me.com/health -> 200, status=ok, mode=hosted
OK   CORS preflight OPTIONS https://api.recommend2me.com/health -> 200, ACAO='https://recommend2me.com'
OK   CORS GET https://api.recommend2me.com/health -> ACAO='https://recommend2me.com'
OK   SPA doğrudan GET https://recommend2me.com/ -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/?_smoke=1785172203 -> 200 + marker
OK   SPA doğrudan GET https://recommend2me.com/board -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/board?_smoke=1785172203 -> 200 + marker
OK   SPA doğrudan GET https://recommend2me.com/scope -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/scope?_smoke=1785172204 -> 200 + marker
OK   SPA doğrudan GET https://recommend2me.com/graph -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/graph?_smoke=1785172204 -> 200 + marker
OK   SPA doğrudan GET https://recommend2me.com/activity -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/activity?_smoke=1785172205 -> 200 + marker
OK   SPA doğrudan GET https://recommend2me.com/ask -> 200 + marker
OK   SPA refresh GET https://recommend2me.com/ask?_smoke=1785172205 -> 200 + marker
SMOKE YEŞİL
```

## 3) BİLİNÇLİ BOZUK HEDEF — kırmızının gerçekten kırmızı olduğu
```
OK   /health github_auth='configured'
OK   /health gemini='configured'
OK   GET https://api.recommend2me.com/health -> 200, status=ok, mode=hosted
FAIL CORS preflight OPTIONS https://api.recommend2me.com/health -> 400 (200/204 bekleniyor)
...
FAIL SPA refresh GET https://example.com/activity?_smoke=1785172221 -> 404
FAIL SPA doğrudan GET https://example.com/ask -> 404
FAIL SPA refresh GET https://example.com/ask?_smoke=1785172221 -> 404
SMOKE KIRMIZI — 14 hata, 0 uyarı
```

Not: bu dosya terminal çıktısının BİREBİR kaydıdır (kopyalanabilir/aranabilir).
Gerçek Windows makinesinde alınacak PNG ekran görüntüsü ayrıca eklenebilir —
CP1252 vakası Windows'a özgü olduğu için onu ancak Windows'ta koşan alabilir.
