# market-data

Bu dal GitHub Actions tarafından otomatik yazılır; elle düzenlemeyin.

- `daily/<kaynak>/<SEMBOL>.csv`: günlük fiyatlar (her iş günü kapanıştan sonra eklenir)
- `reports/<isim>.json`: haftalık walk-forward araştırma raporları

Bu bir analizdir; buradaki hiçbir şey emir ya da yatırım tavsiyesi değildir.

## Durum
Son çalışma: **Haftalık araştırma**, 2026-11-28 15:40 UTC

### Veri
| Kaynak | Hisse | En güncel gün | En geride kalan |
|---|---|---|---|
| evds | 2 | 2026-11-27 | hepsi güncel |
| yahoo_bist | 44 | 2026-11-27 | TAVHL (2026-11-26) |
| yahoo_us | 31 | 2026-11-27 | SKYT (2026-07-30) |

### Haftalık araştırma
| Rapor | Tür | Tarih | Model | IC t | Toplam (model) | Seçilen strateji → gelecek hafta |
|---|---|---|---|---|---|---|
| bist_likit | sıralama (31/44 elemeden geçti) | 2026-11-28 | FAIL ❌ | 0.31 | -38.8% | **boosting** [ZAYIF]: PGSUS, YKBNK, VAKBN, AKSEN, MGROS |
| smtk_peers | sıralama (15/30 elemeden geçti) | 2026-11-28 | FAIL ❌ | -0.89 | -95.2% | **yok** [YOK]: hisse seçme, endeksi tut |
| smtk_timeseries | tek hisse | 2026-11-28 | FAIL ❌ | -0.80 | -66.4% | SMTK FLAT _(model FAIL: sinyal değil)_ |

#### bist_gorunum: gelecek hafta risk (2026-11-26 kapanışı)
Doğrulama: 462 haftanın %70'inde hareket büyüklüğünü doğru sıraladı (t 11.97); %80'lik aralık gerçekte %77 kapsadı.
| Sıra | Hisse | Beklenen hareket | Olası aralık (%) | Olası aralık (fiyat) |
|---|---|---|---|---|
| 1 | AKSEN | ±5.9% | -7.8% … +10.5% | 54.77 – 65.65 |
| 2 | HEKTS | ±5.2% | -7.0% … +9.4% | 1.46 – 1.72 |
| 3 | TTKOM | ±5.1% | -6.8% … +9.2% | 41.70 – 48.88 |
| 4 | GUBRF | ±5.1% | -6.8% … +9.2% | 258.16 – 302.39 |
| 5 | TOASO | ±5.1% | -6.8% … +9.1% | 228.21 – 267.16 |
| 6 | THYAO | ±5.1% | -6.7% … +9.1% | 288.95 – 337.78 |
| 7 | VAKBN | ±5.1% | -6.7% … +9.0% | 29.46 – 34.44 |
| 8 | PETKM | ±5.0% | -6.7% … +9.0% | 14.39 – 16.81 |
| 9 | MGROS | ±5.0% | -6.7% … +9.0% | 373.07 – 435.71 |
| 10 | ISCTR | ±4.9% | -6.4% … +8.7% | 11.05 – 12.84 |

#### bist_gorunum: 3-6 aylık sıralama
En iyi sonuç: göstergeleri birlikte tartan doğrusal model, 26 hafta tutulduğunda. Grubun ortalamasına göre dönem başına +8.0% (yıllık +16.6%), 17 dönemin %65'inde önde; t=2.09 (eşik 2.64); son 2 yılda da tuttu. Güven: ORTA.

İlk hisseler: VAKBN, THYAO, TTKOM, TOASO, PETKM (tüm liste `reports/bist_gorunum_siralama.csv`, risk `reports/bist_gorunum_risk.csv`).

#### bist_likit: 2026-11-26 kapanışına göre gelecek hafta (strateji: boosting)
| Sıra | Hisse | Beklenen fazla getiri | Kıyası yenme olasılığı | Seçildi |
|---|---|---|---|---|
| 1 | PGSUS | +0.0% | %45 | ✅ |
| 2 | YKBNK | +0.0% | %45 | ✅ |
| 3 | VAKBN | +0.0% | %45 | ✅ |
| 4 | AKSEN | +0.0% | %45 | ✅ |
| 5 | MGROS | +0.0% | %45 | ✅ |
| 6 | THYAO | +0.0% | %45 |  |
| 7 | EKGYO | +0.0% | %45 |  |
| 8 | EREGL | +0.0% | %45 |  |
| 9 | FROTO | +0.0% | %45 |  |
| 10 | ISCTR | +0.0% | %45 |  |

Geçmiş karne: 353 haftanın %53'inde seçilen hisseler kıyası (universe_ew) yendi; haftalık ortalama +0.2% (masraf öncesi). Tüm liste: `reports/bist_likit_tahmin.csv`, hafta hafta geçmiş: `reports/bist_likit_gecmis.csv`.
