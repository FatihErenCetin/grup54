# Daily Scrum Log — Sprint 2 (6 – 19 Temmuz 2026)

> **Platform:** **Slack** (danışman dahil grup) + ekip-içi **WhatsApp** — ikisi birden, **yazılı async, sabit saat yok**. Görsel kanıtlar bu klasörde (`daily-*.png`) ve `../Meetings/` klasöründedir.
> AI bu tabloyu mesaj/toplantı/PR kayıtlarından taslakladı; SM tarafından doğrulanmıştır (D-14).

| Tarih | Öne çıkanlar (dün/bugün) | Blocker/Karar | Kanıt |
|---|---|---|---|
| 2026-07-08 | Sprint 2 açılışı — ilk planlama toplantısı: görev dağılımı yapıldı, bağımlılık haritası çıkarıldı (bkz. #108/#109) | Enes Talha Erdem bu toplantıya katılmadı | `../Meetings/sprint2-planning-2026-07-08.png` |
| 2026-07-09 | Fatih Enes+Semih'e yeni görev/PR review ataması yaptı; Semih review backlog'unu temizledi (approve: #113/#117/#119/#121/#128; değişiklik istedi: #115, #123); Fatih #46 GitHub App key dosyasını (.pem) Esma'ya paylaşıp reviewer atadı | — | `daily-2026-07-09-whatsapp.png` |
| 2026-07-10 | Esma #46/PR #132'de Windows'ta key doğrulamasını kıran bir hatayı düzeltip PR'a commit'ledi (Fatih merge'leyecek); #50/#26/#16/#25 (PR #135-138) tamamlanıp Enes'ten review istendi; bağımlılık haritasının güncellenmesi Fatih'e hatırlatıldı | #135-138 henüz review almadı → #24 bekliyor | `daily-2026-07-10-whatsapp.png` |
| 2026-07-11 | Enes #140'ı onayladı (merge edildi); Enes #41 (PR #141) + #47 (PR #142) işlerini tamamlayıp Esma'yı reviewer atadı; Esma ikisini review edip aynı bug'ı buldu (`PresenceRow.from_harness` yanlış şema alanları — presence.task/since NULL kalıyordu), düzeltip her iki PR'a da commit'ledi (merge Enes'te); Enes sıradaki işi (#28 Eval runner) için #17/#27 bağımlılığını bekliyor | Enes #17 (Semih) + #27 (Fatih) bekliyor — blocker yemiş durumda | `daily-2026-07-11-whatsapp.png` |
| 2026-07-12 | Enes #144 (JudgePort imza güncellemesi: `sim: float\|None`, ilgili tüm adapter/gate/kontrat dosyaları) + #28 (Eval runner) işlerini tamamladı, Fatih'e merge için haber verdi; Fatih #144 + #111 (CORS) merge etti, #143'ü onayladı (Semih merge edecek); kontrat Ek C'de `ConflictCase.sim` donduruldu (None = benzerliği dedektör hesaplar); Fatih T-44'ü (Esma'nın daily kanıt PR'ı) de review etti; Esma #145'i (Fatih'in OpenAPI client PR'ı) review edip onayladı | — | `daily-2026-07-12-whatsapp.png` |
