# market-data

Bu dal GitHub Actions tarafından otomatik yazılır; elle düzenlemeyin.

- `daily/<kaynak>/<SEMBOL>.csv`: günlük fiyatlar (her iş günü kapanıştan sonra eklenir)
- `reports/<isim>.json`: haftalık walk-forward araştırma raporları

Bu bir analizdir; buradaki hiçbir şey emir ya da yatırım tavsiyesi değildir.

## Durum
Son çalışma: **Haftalık araştırma**, 2026-10-31 12:45 UTC

### Veri
| Kaynak | Hisse | En güncel gün | En geride kalan |
|---|---|---|---|
| evds | 2 | 2026-10-30 | hepsi güncel |
| yahoo_bist | 44 | 2026-10-28 | hepsi güncel |
| yahoo_us | 31 | 2026-10-29 | SKYT (2026-07-30) |

### Haftalık araştırma
| Rapor | Tür | Tarih | Model | IC t | Toplam (model) | Seçilen strateji → gelecek hafta |
|---|---|---|---|---|---|---|
| bist_likit | sıralama (31/44 elemeden geçti) | 2026-10-31 | FAIL ❌ | 0.24 | -33.6% | **yok** [YOK]: hisse seçme, endeksi tut |
| smtk_peers | sıralama (14/30 elemeden geçti) | 2026-10-31 | FAIL ❌ | -0.73 | -95.6% | **yok** [YOK]: hisse seçme, endeksi tut |
| smtk_timeseries | tek hisse | 2026-10-31 | FAIL ❌ | -0.33 | -54.2% | SMTK FLAT _(model FAIL: sinyal değil)_ |

#### bist_gorunum: gelecek hafta risk (2026-10-28 kapanışı)
Doğrulama: 458 haftanın %70'inde hareket büyüklüğünü doğru sıraladı (t 12.07); %80'lik aralık gerçekte %77 kapsadı.
| Sıra | Hisse | Beklenen hareket | Olası aralık (%) | Olası aralık (fiyat) |
|---|---|---|---|---|
| 1 | AKSEN | ±5.8% | -7.7% … +10.4% | 62.11 – 74.31 |
| 2 | HEKTS | ±5.5% | -7.2% … +9.8% | 1.47 – 1.73 |
| 3 | HALKB | ±5.1% | -6.7% … +9.1% | 40.23 – 47.07 |
| 4 | GUBRF | ±4.9% | -6.5% … +8.8% | 259.87 – 302.47 |
| 5 | PETKM | ±4.8% | -6.4% … +8.6% | 16.39 – 19.00 |
| 6 | FROTO | ±4.5% | -6.0% … +8.1% | 65.07 – 74.77 |
| 7 | ALARK | ±4.3% | -5.7% … +7.7% | 88.90 – 101.60 |
| 8 | TOASO | ±4.3% | -5.7% … +7.7% | 216.82 – 247.79 |
| 9 | VAKBN | ±4.3% | -5.7% … +7.7% | 28.87 – 32.98 |
| 10 | KRDMD | ±4.3% | -5.6% … +7.6% | 35.44 – 40.42 |

#### bist_gorunum: 3-6 aylık sıralama
En iyi sonuç: göstergeleri birlikte tartan doğrusal model, 26 hafta tutulduğunda. Grubun ortalamasına göre dönem başına +8.0% (yıllık +16.6%), 17 dönemin %65'inde önde; t=2.09 (eşik 2.64); son 2 yılda da tuttu. Güven: ORTA.

İlk hisseler: HALKB, TUPRS, PETKM, VAKBN, KRDMD (tüm liste `reports/bist_gorunum_siralama.csv`, risk `reports/bist_gorunum_risk.csv`).
