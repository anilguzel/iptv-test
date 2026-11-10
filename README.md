# market-data

Bu dal GitHub Actions tarafından otomatik yazılır; elle düzenlemeyin.

- `daily/<kaynak>/<SEMBOL>.csv`: günlük fiyatlar (her iş günü kapanıştan sonra eklenir)
- `reports/<isim>.json`: haftalık walk-forward araştırma raporları

Bu bir analizdir; buradaki hiçbir şey emir ya da yatırım tavsiyesi değildir.

## Durum
Son çalışma: **Günlük veri toplama**, 2026-11-10 03:49 UTC

### Veri
| Kaynak | Hisse | En güncel gün | En geride kalan |
|---|---|---|---|
| evds | 2 | 2026-11-10 | hepsi güncel |
| yahoo_bist | 44 | 2026-11-09 | ZOREN (2026-11-06) |
| yahoo_us | 31 | 2026-11-09 | SKYT (2026-07-30) |

### Haftalık araştırma
| Rapor | Tür | Tarih | Model | IC t | Toplam (model) | Seçilen strateji → gelecek hafta |
|---|---|---|---|---|---|---|
| bist_likit | sıralama (31/44 elemeden geçti) | 2026-11-07 | FAIL ❌ | 0.20 | -39.8% | **boosting** [ZAYIF]: HALKB, THYAO, YKBNK, SAHOL, TAVHL |
| smtk_peers | sıralama (14/30 elemeden geçti) | 2026-11-07 | FAIL ❌ | -0.69 | -95.4% | **yok** [YOK]: hisse seçme, endeksi tut |
| smtk_timeseries | tek hisse | 2026-11-07 | FAIL ❌ | -0.55 | -54.6% | SMTK FLAT _(model FAIL: sinyal değil)_ |

#### bist_gorunum: gelecek hafta risk (2026-11-05 kapanışı)
Doğrulama: 459 haftanın %70'inde hareket büyüklüğünü doğru sıraladı (t 12.04); %80'lik aralık gerçekte %77 kapsadı.
| Sıra | Hisse | Beklenen hareket | Olası aralık (%) | Olası aralık (fiyat) |
|---|---|---|---|---|
| 1 | GUBRF | ±7.4% | -9.8% … +13.2% | 261.49 – 327.98 |
| 2 | THYAO | ±7.0% | -9.3% … +12.5% | 269.51 – 334.19 |
| 3 | PGSUS | ±6.8% | -9.0% … +12.2% | 127.30 – 156.94 |
| 4 | HEKTS | ±6.6% | -8.7% … +11.8% | 1.66 – 2.03 |
| 5 | AKSEN | ±6.4% | -8.5% … +11.5% | 60.87 – 74.24 |
| 6 | PETKM | ±6.3% | -8.4% … +11.4% | 15.46 – 18.80 |
| 7 | TAVHL | ±6.0% | -8.0% … +10.8% | 267.79 – 322.41 |
| 8 | HALKB | ±5.7% | -7.6% … +10.2% | 37.07 – 44.20 |
| 9 | KRDMD | ±5.6% | -7.5% … +10.1% | 33.98 – 40.43 |
| 10 | SISE | ±5.6% | -7.4% … +10.0% | 32.80 – 38.96 |

#### bist_gorunum: 3-6 aylık sıralama
En iyi sonuç: göstergeleri birlikte tartan doğrusal model, 26 hafta tutulduğunda. Grubun ortalamasına göre dönem başına +8.0% (yıllık +16.6%), 17 dönemin %65'inde önde; t=2.09 (eşik 2.64); son 2 yılda da tuttu. Güven: ORTA.

İlk hisseler: HALKB, VAKBN, PETKM, TAVHL, THYAO (tüm liste `reports/bist_gorunum_siralama.csv`, risk `reports/bist_gorunum_risk.csv`).

#### bist_likit: 2026-11-05 kapanışına göre gelecek hafta (strateji: boosting)
| Sıra | Hisse | Beklenen fazla getiri | Kıyası yenme olasılığı | Seçildi |
|---|---|---|---|---|
| 1 | HALKB | +0.1% | %47 | ✅ |
| 2 | THYAO | +0.1% | %47 | ✅ |
| 3 | YKBNK | +0.1% | %46 | ✅ |
| 4 | SAHOL | +0.1% | %46 | ✅ |
| 5 | TAVHL | +0.1% | %46 | ✅ |
| 6 | ENKAI | +0.1% | %46 |  |
| 7 | KCHOL | +0.1% | %46 |  |
| 8 | FROTO | +0.1% | %46 |  |
| 9 | VAKBN | +0.1% | %46 |  |
| 10 | TOASO | +0.0% | %46 |  |

Geçmiş karne: 353 haftanın %54'inde seçilen hisseler kıyası (universe_ew) yendi; haftalık ortalama +0.2% (masraf öncesi). Tüm liste: `reports/bist_likit_tahmin.csv`, hafta hafta geçmiş: `reports/bist_likit_gecmis.csv`.
