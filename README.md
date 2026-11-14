# market-data

Bu dal GitHub Actions tarafından otomatik yazılır; elle düzenlemeyin.

- `daily/<kaynak>/<SEMBOL>.csv`: günlük fiyatlar (her iş günü kapanıştan sonra eklenir)
- `reports/<isim>.json`: haftalık walk-forward araştırma raporları

Bu bir analizdir; buradaki hiçbir şey emir ya da yatırım tavsiyesi değildir.

## Durum
Son çalışma: **Haftalık araştırma**, 2026-11-14 13:39 UTC

### Veri
| Kaynak | Hisse | En güncel gün | En geride kalan |
|---|---|---|---|
| evds | 2 | 2026-11-13 | hepsi güncel |
| yahoo_bist | 44 | 2026-11-13 | ZOREN (2026-11-12) |
| yahoo_us | 31 | 2026-11-13 | SKYT (2026-07-30) |

### Haftalık araştırma
| Rapor | Tür | Tarih | Model | IC t | Toplam (model) | Seçilen strateji → gelecek hafta |
|---|---|---|---|---|---|---|
| bist_likit | sıralama (31/44 elemeden geçti) | 2026-11-14 | FAIL ❌ | 0.16 | -37.4% | **boosting** [ZAYIF]: TUPRS, HALKB, GARAN, PGSUS, TTKOM |
| smtk_peers | sıralama (15/30 elemeden geçti) | 2026-11-14 | FAIL ❌ | -0.79 | -95.5% | **yok** [YOK]: hisse seçme, endeksi tut |
| smtk_timeseries | tek hisse | 2026-11-14 | FAIL ❌ | -0.46 | -68.0% | SMTK FLAT _(model FAIL: sinyal değil)_ |

#### bist_gorunum: gelecek hafta risk (2026-11-12 kapanışı)
Doğrulama: 460 haftanın %70'inde hareket büyüklüğünü doğru sıraladı (t 12.07); %80'lik aralık gerçekte %77 kapsadı.
| Sıra | Hisse | Beklenen hareket | Olası aralık (%) | Olası aralık (fiyat) |
|---|---|---|---|---|
| 1 | GUBRF | ±6.0% | -7.9% … +10.7% | 258.28 – 310.60 |
| 2 | PGSUS | ±5.8% | -7.7% … +10.5% | 145.99 – 174.75 |
| 3 | HALKB | ±5.5% | -7.3% … +9.9% | 39.97 – 47.39 |
| 4 | HEKTS | ±5.4% | -7.1% … +9.6% | 1.58 – 1.86 |
| 5 | THYAO | ±5.2% | -6.9% … +9.3% | 296.99 – 348.82 |
| 6 | ALARK | ±4.8% | -6.4% … +8.6% | 99.89 – 115.93 |
| 7 | EKGYO | ±4.7% | -6.3% … +8.5% | 17.63 – 20.41 |
| 8 | AKSEN | ±4.7% | -6.2% … +8.3% | 67.10 – 77.46 |
| 9 | TOASO | ±4.7% | -6.2% … +8.3% | 223.35 – 257.85 |
| 10 | TTKOM | ±4.6% | -6.1% … +8.3% | 47.47 – 54.73 |

#### bist_gorunum: 3-6 aylık sıralama
En iyi sonuç: göstergeleri birlikte tartan doğrusal model, 26 hafta tutulduğunda. Grubun ortalamasına göre dönem başına +8.0% (yıllık +16.7%), 17 dönemin %65'inde önde; t=2.09 (eşik 2.64); son 2 yılda da tuttu. Güven: ORTA.

İlk hisseler: HALKB, PGSUS, VAKBN, THYAO, GARAN (tüm liste `reports/bist_gorunum_siralama.csv`, risk `reports/bist_gorunum_risk.csv`).

#### bist_likit: 2026-11-12 kapanışına göre gelecek hafta (strateji: boosting)
| Sıra | Hisse | Beklenen fazla getiri | Kıyası yenme olasılığı | Seçildi |
|---|---|---|---|---|
| 1 | TUPRS | +0.1% | %46 | ✅ |
| 2 | HALKB | +0.1% | %46 | ✅ |
| 3 | GARAN | +0.1% | %46 | ✅ |
| 4 | PGSUS | +0.1% | %46 | ✅ |
| 5 | TTKOM | +0.1% | %46 | ✅ |
| 6 | AKBNK | +0.1% | %46 |  |
| 7 | ISCTR | +0.1% | %46 |  |
| 8 | BIMAS | +0.1% | %46 |  |
| 9 | FROTO | +0.1% | %46 |  |
| 10 | KCHOL | +0.1% | %46 |  |

Geçmiş karne: 353 haftanın %53'inde seçilen hisseler kıyası (universe_ew) yendi; haftalık ortalama +0.2% (masraf öncesi). Tüm liste: `reports/bist_likit_tahmin.csv`, hafta hafta geçmiş: `reports/bist_likit_gecmis.csv`.
