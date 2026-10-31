# market-data

Bu dal GitHub Actions tarafından otomatik yazılır; elle düzenlemeyin.

- `daily/<kaynak>/<SEMBOL>.csv`: günlük fiyatlar (her iş günü kapanıştan sonra eklenir)
- `reports/<isim>.json`: haftalık walk-forward araştırma raporları

Bu bir analizdir; buradaki hiçbir şey emir ya da yatırım tavsiyesi değildir.

## Durum
Son çalışma: **Günlük veri toplama**, 2026-10-31 01:05 UTC

### Veri
| Kaynak | Hisse | En güncel gün | En geride kalan |
|---|---|---|---|
| evds | 2 | 2026-10-30 | hepsi güncel |
| yahoo_bist | 44 | 2026-10-28 | hepsi güncel |
| yahoo_us | 31 | 2026-10-29 | SKYT (2026-07-30) |

### Haftalık araştırma
| Rapor | Tür | Tarih | Model | IC t | Toplam (model) | Seçilen strateji → gelecek hafta |
|---|---|---|---|---|---|---|
| bist_likit | sıralama (31/44 elemeden geçti) | 2026-10-28 | FAIL ❌ | 0.23 | -33.7% | **boosting** [ZAYIF]: TCELL, HALKB, SISE, VAKBN, TUPRS |
| smtk_peers | sıralama (14/30 elemeden geçti) | 2026-10-28 | FAIL ❌ | -0.73 | -95.6% | **yok** [YOK]: hisse seçme, endeksi tut |
| smtk_timeseries | tek hisse | 2026-10-28 | FAIL ❌ | -0.33 | -54.2% | SMTK LONG _(model FAIL: sinyal değil)_ |

#### bist_gorunum: gelecek hafta risk (2026-10-26 kapanışı)
Doğrulama: 458 haftanın %70'inde hareket büyüklüğünü doğru sıraladı (t 12.11); %80'lik aralık gerçekte %77 kapsadı.
| Sıra | Hisse | Beklenen hareket | Olası aralık (%) | Olası aralık (fiyat) |
|---|---|---|---|---|
| 1 | GUBRF | ±4.9% | -6.5% … +8.8% | 256.31 – 298.50 |
| 2 | AKSEN | ±4.9% | -6.5% … +8.8% | 60.11 – 69.97 |
| 3 | HALKB | ±4.8% | -6.3% … +8.6% | 40.22 – 46.62 |
| 4 | PETKM | ±4.7% | -6.2% … +8.4% | 16.61 – 19.22 |
| 5 | FROTO | ±4.4% | -5.9% … +8.0% | 63.95 – 73.36 |
| 6 | HEKTS | ±4.4% | -5.8% … +7.9% | 1.60 – 1.83 |
| 7 | KRDMD | ±4.4% | -5.8% … +7.8% | 33.98 – 38.87 |
| 8 | TTKOM | ±4.0% | -5.3% … +7.2% | 44.30 – 50.18 |
| 9 | VAKBN | ±3.9% | -5.1% … +7.0% | 28.63 – 32.28 |
| 10 | SISE | ±3.8% | -5.1% … +6.9% | 32.66 – 36.76 |

#### bist_gorunum: 3-6 aylık sıralama
En iyi sonuç: göstergeleri birlikte tartan doğrusal model, 26 hafta tutulduğunda. Grubun ortalamasına göre dönem başına +8.0% (yıllık +16.6%), 17 dönemin %65'inde önde; t=2.09 (eşik 2.64); son 2 yılda da tuttu. Güven: ORTA.

İlk hisseler: HALKB, TUPRS, PETKM, KRDMD, VAKBN (tüm liste `reports/bist_gorunum_siralama.csv`, risk `reports/bist_gorunum_risk.csv`).

#### bist_likit: 2026-10-26 kapanışına göre gelecek hafta (strateji: boosting)
| Sıra | Hisse | Beklenen fazla getiri | Kıyası yenme olasılığı | Seçildi |
|---|---|---|---|---|
| 1 | TCELL | +0.1% | %45 | ✅ |
| 2 | HALKB | +0.1% | %45 | ✅ |
| 3 | SISE | +0.1% | %45 | ✅ |
| 4 | VAKBN | +0.1% | %45 | ✅ |
| 5 | TUPRS | +0.0% | %45 | ✅ |
| 6 | ENKAI | +0.0% | %45 |  |
| 7 | TTKOM | +0.0% | %45 |  |
| 8 | ULKER | +0.0% | %45 |  |
| 9 | ASELS | +0.0% | %45 |  |
| 10 | ALARK | +0.0% | %45 |  |

Geçmiş karne: 353 haftanın %53'inde seçilen hisseler kıyası (universe_ew) yendi; haftalık ortalama +0.2% (masraf öncesi). Tüm liste: `reports/bist_likit_tahmin.csv`, hafta hafta geçmiş: `reports/bist_likit_gecmis.csv`.
