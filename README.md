# market-data

Bu dal GitHub Actions tarafından otomatik yazılır; elle düzenlemeyin.

- `daily/<kaynak>/<SEMBOL>.csv`: günlük fiyatlar (her iş günü kapanıştan sonra eklenir)
- `reports/<isim>.json`: haftalık walk-forward araştırma raporları

Bu bir analizdir; buradaki hiçbir şey emir ya da yatırım tavsiyesi değildir.

## Durum
Son çalışma: **Günlük veri toplama**, 2026-11-27 03:49 UTC

### Veri
| Kaynak | Hisse | En güncel gün | En geride kalan |
|---|---|---|---|
| evds | 2 | 2026-11-27 | hepsi güncel |
| yahoo_bist | 44 | 2026-11-26 | THYAO (2026-11-25) |
| yahoo_us | 31 | 2026-11-25 | SKYT (2026-07-30) |

### Haftalık araştırma
| Rapor | Tür | Tarih | Model | IC t | Toplam (model) | Seçilen strateji → gelecek hafta |
|---|---|---|---|---|---|---|
| bist_likit | sıralama (31/44 elemeden geçti) | 2026-11-21 | FAIL ❌ | 0.28 | -36.3% | **yok** [YOK]: hisse seçme, endeksi tut |
| smtk_peers | sıralama (15/30 elemeden geçti) | 2026-11-21 | FAIL ❌ | -0.88 | -95.5% | **yok** [YOK]: hisse seçme, endeksi tut |
| smtk_timeseries | tek hisse | 2026-11-21 | FAIL ❌ | -0.52 | -66.1% | SMTK FLAT _(model FAIL: sinyal değil)_ |

#### bist_gorunum: gelecek hafta risk (2026-11-19 kapanışı)
Doğrulama: 461 haftanın %70'inde hareket büyüklüğünü doğru sıraladı (t 12.04); %80'lik aralık gerçekte %77 kapsadı.
| Sıra | Hisse | Beklenen hareket | Olası aralık (%) | Olası aralık (fiyat) |
|---|---|---|---|---|
| 1 | PETKM | ±5.4% | -7.1% … +9.7% | 14.29 – 16.88 |
| 2 | GUBRF | ±5.3% | -7.0% … +9.5% | 254.47 – 299.82 |
| 3 | HEKTS | ±5.2% | -6.9% … +9.3% | 1.47 – 1.73 |
| 4 | AKSEN | ±5.2% | -6.9% … +9.3% | 62.26 – 73.06 |
| 5 | PGSUS | ±5.0% | -6.7% … +9.0% | 146.18 – 170.69 |
| 6 | TTKOM | ±4.8% | -6.3% … +8.5% | 45.72 – 52.96 |
| 7 | ULKER | ±4.7% | -6.2% … +8.4% | 64.22 – 74.29 |
| 8 | SISE | ±4.7% | -6.2% … +8.4% | 31.24 – 36.13 |
| 9 | TOASO | ±4.6% | -6.1% … +8.2% | 234.17 – 269.76 |
| 10 | HALKB | ±4.6% | -6.0% … +8.2% | 37.71 – 43.42 |

#### bist_gorunum: 3-6 aylık sıralama
En iyi sonuç: göstergeleri birlikte tartan doğrusal model, 26 hafta tutulduğunda. Grubun ortalamasına göre dönem başına +8.0% (yıllık +16.7%), 17 dönemin %65'inde önde; t=2.09 (eşik 2.64); son 2 yılda da tuttu. Güven: ORTA.

İlk hisseler: TTKOM, PETKM, PGSUS, VAKBN, THYAO (tüm liste `reports/bist_gorunum_siralama.csv`, risk `reports/bist_gorunum_risk.csv`).
