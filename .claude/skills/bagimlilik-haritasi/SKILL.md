---
name: bagimlilik-haritasi
description: Bir sprint/milestone için bağımlılık haritası + yürütme sırası belgesi üret. Kullanım - /bagimlilik-haritasi <milestone adı> (örn. "Sprint 3"). Rehber docs/bagimlilik-harita-rehberi.md'dedir; örnek çıktı docs/sprint2-bagimlilik.md.
---

1. **`docs/bagimlilik-harita-rehberi.md`'yi OKU** — veri toplama, bağımlılık çıkarımı (sert/yumuşak), 5-bölümlük format ve kalite kontrolleri oradadır (tek kaynak; burada tekrar yok).
2. `$ARGUMENTS` ile verilen milestone için rehberi uygula; örnek iskelet olarak `docs/sprint2-bagimlilik.md`'yi kullan. `$ARGUMENTS` boşsa kullanıcıdan milestone adını iste.
3. Çıktıyı `docs/<milestone-slug>-bagimlilik.md`'ye yaz; **konvansiyonel akışla** (issue + branch + `Closes #N` PR) yayınla — doğrudan main'e yazma. Şüpheli bağımlılıkları PO'ya sorulacaklar listesi olarak raporla.
