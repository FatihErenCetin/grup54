"""Sabit şema + kaybolmama mekaniği (#340, §8.5) — deterministik çekirdek."""

from ensemble.onboarding.intake import (
    ALAN_IDLERI,
    MAKS_BOSLUK_TURU,
    Brief,
    Kisitlar,
    Varsayim,
    ana_sorular,
    bosluk_sorulari,
    cevaplari_briefe_cevir,
    eksik_alanlar,
    uyarilar,
)


def _dolu_brief() -> Brief:
    return Brief(
        urun_tek_cumle="Yazılım ekipleri için çakışmaları erken gösteren bir radar.",
        hedef_kullanicilar=["geliştirici", "takım lideri"],
        cekirdek_ozellikler=["çakışma radarı", "scope bekçisi", "board"],
        kapsam_disi=["mobil uygulama"],
        kisitlar=Kisitlar(ekip_buyuklugu=4, sprint_sayisi=3),
        basari_hedefi="Canlı demoda iki geliştiricinin çakışması radarda görünsün.",
    )


def test_ana_sorular_her_alan_icin_tek_soru():
    """§8.5 'her alan için 1 ana soru' — ne eksik ne fazla."""
    sorular = ana_sorular()
    assert [s.alan for s in sorular] == list(ALAN_IDLERI)
    assert len(sorular) == len(set(s.alan for s in sorular))


def test_dolu_brief_eksik_alan_uretmez():
    assert eksik_alanlar(_dolu_brief()) == []


def test_bos_brief_alti_alanin_hepsini_eksik_isaretler():
    eksikler = eksik_alanlar(Brief())
    assert {e.alan for e in eksikler} == set(ALAN_IDLERI)


def test_yetersiz_cekirdek_ozellik_uydurulmaz_isaretlenir():
    """Kabul kriteri: 'eksik alan UYDURULMAZ, işaretlenir'.

    İki madde MVP kapsamı çizmez -> 'yetersiz'. Doldurulmaz, raporlanır.
    """
    brief = _dolu_brief()
    brief.cekirdek_ozellikler = ["çakışma radarı", "board"]
    eksikler = {e.alan: e for e in eksik_alanlar(brief)}
    assert eksikler["cekirdek_ozellikler"].neden == "yetersiz"
    # Uydurmadık: liste AYNEN kaldı.
    assert brief.cekirdek_ozellikler == ["çakışma radarı", "board"]


def test_kisitlar_sprint_dagitimina_yetmiyorsa_yetersiz():
    brief = _dolu_brief()
    brief.kisitlar = Kisitlar(ekip_buyuklugu=4, sprint_sayisi=None, teknolojiler=["Python"])
    eksikler = {e.alan: e for e in eksik_alanlar(brief)}
    assert eksikler["kisitlar"].neden == "yetersiz"
    assert "sprint sayısı" in eksikler["kisitlar"].aciklama.lower()


def test_bosluk_sorulari_yalniz_eksik_alanlari_sorar():
    """Sorgu yağmuru yasağı: dolu alan İKİNCİ KEZ sorulmaz."""
    brief = _dolu_brief()
    brief.kapsam_disi = []
    sorular = bosluk_sorulari(brief, tur=2)
    assert [s.alan for s in sorular] == ["kapsam_disi"]


def test_bosluk_sorulari_ikinci_turdan_sonra_susar():
    """§8.5 'en çok iki tur' — üçüncü tur YOK."""
    bos = Brief()
    assert bosluk_sorulari(bos, tur=MAKS_BOSLUK_TURU) != []
    assert bosluk_sorulari(bos, tur=MAKS_BOSLUK_TURU + 1) == []


def test_cevaplar_semaya_mekanik_oturur():
    brief = cevaplari_briefe_cevir(
        {
            "urun_tek_cumle": "  Ekipler için ortak proje beyni.  ",
            "hedef_kullanicilar": "- geliştirici\n- ürün sahibi\n\n",
            "cekirdek_ozellikler": "radar; board; scope",
            "kisitlar": "4 kişi, 3 sprint, 14 gün",
        }
    )
    assert brief.urun_tek_cumle == "Ekipler için ortak proje beyni."
    assert brief.hedef_kullanicilar == ["geliştirici", "ürün sahibi"]
    assert brief.cekirdek_ozellikler == ["radar", "board", "scope"]
    assert brief.kisitlar.ekip_buyuklugu == 4
    assert brief.kisitlar.sprint_sayisi == 3
    assert brief.kisitlar.sprint_gun == 14


def test_kisit_ayiklama_etiketsiz_sayiyi_uydurmaz():
    """'12' tek başına hiçbir alana yazılmaz — yanlış alana sayı koymaktansa boş."""
    brief = cevaplari_briefe_cevir({"kisitlar": "12"})
    assert brief.kisitlar.ekip_buyuklugu is None
    assert brief.kisitlar.sprint_sayisi is None


def test_elle_doldurulan_alanin_ai_varsayimi_silinir():
    """Kullanıcı kendi cümlesini yazdıysa o alan artık 'AI varsaydı' değildir."""
    brief = Brief(
        urun_tek_cumle="AI'nın varsaydığı cümle",
        varsayimlar=[Varsayim(alan="urun_tek_cumle", deger_ozeti="...", gerekce="...")],
    )
    yeni = cevaplari_briefe_cevir({"urun_tek_cumle": "Kullanıcının kendi cümlesi."}, brief)
    assert yeni.urun_tek_cumle == "Kullanıcının kendi cümlesi."
    assert yeni.varsayimlar == []


def test_yediden_fazla_ozellik_uyari_verir_ama_engellemez():
    brief = _dolu_brief()
    brief.cekirdek_ozellikler = [f"özellik {i}" for i in range(9)]
    assert eksik_alanlar(brief) == []
    assert [u.alan for u in uyarilar(brief)] == ["cekirdek_ozellikler"]
