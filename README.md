# market-data

Bu dal GitHub Actions tarafından otomatik yazılır; elle düzenlemeyin.

- `daily/<kaynak>/<SEMBOL>.csv`: günlük fiyatlar (her iş günü kapanıştan sonra eklenir)
- `reports/<isim>.json`: haftalık walk-forward araştırma raporları

Bu bir analizdir; buradaki hiçbir şey emir ya da yatırım tavsiyesi değildir.

## Durum
Son çalışma: **Haftalık araştırma**, 2026-10-28 10:23 UTC

### Veri
| Kaynak | Hisse | En güncel gün | En geride kalan |
|---|---|---|---|
| yahoo_bist | 44 | 2026-10-26 | hepsi güncel |
| yahoo_us | 31 | 2026-10-26 | SKYT (2026-07-30) |

### Haftalık araştırma
| Rapor | Tür | Tarih | Model | IC t | Toplam (model) | Seçilen strateji → gelecek hafta |
|---|---|---|---|---|---|---|
| bist_likit | sıralama (31/44 elemeden geçti) | 2026-10-28 | FAIL ❌ | 0.46 | +38.0% | **near_high_12w** [ZAYIF]: YKBNK, GARAN, TAVHL, SAHOL, TUPRS |
| smtk_peers | sıralama (14/30 elemeden geçti) | 2026-10-28 | FAIL ❌ | -0.73 | -65.2% | **low_vol_12w** [ZAYIF]: PLAB, LASR, AMBA, POET, KLIC |
| smtk_timeseries | tek hisse | 2026-10-28 | FAIL ❌ | -0.33 | -54.2% | SMTK LONG _(model FAIL: sinyal değil)_ |

#### bist_likit: 2026-10-26 kapanışına göre gelecek hafta (strateji: near_high_12w)
| Sıra | Hisse | Beklenen fazla getiri | Kıyası yenme olasılığı | Seçildi |
|---|---|---|---|---|
| 1 | YKBNK | +0.3% | %50 | ✅ |
| 2 | GARAN | +0.3% | %50 | ✅ |
| 3 | TAVHL | +0.3% | %50 | ✅ |
| 4 | SAHOL | +0.3% | %50 | ✅ |
| 5 | TUPRS | +0.3% | %50 | ✅ |
| 6 | KCHOL | +0.3% | %50 |  |
| 7 | AKBNK | +0.2% | %48 |  |
| 8 | TCELL | +0.2% | %48 |  |
| 9 | BIMAS | +0.2% | %48 |  |
| 10 | ISCTR | +0.2% | %48 |  |

Geçmiş karne: 353 haftanın %55'inde seçilen hisseler kıyası (XU100) yendi; haftalık ortalama +0.3% (masraf öncesi). Tüm liste: `reports/bist_likit_tahmin.csv`, hafta hafta geçmiş: `reports/bist_likit_gecmis.csv`.

#### smtk_peers: 2026-10-26 kapanışına göre gelecek hafta (strateji: low_vol_12w)
| Sıra | Hisse | Beklenen fazla getiri | Kıyası yenme olasılığı | Seçildi |
|---|---|---|---|---|
| 1 | PLAB | -0.0% | %48 | ✅ |
| 2 | LASR | -0.0% | %48 | ✅ |
| 3 | AMBA | +0.7% | %51 | ✅ |
| 4 | POET | +0.7% | %51 | ✅ |
| 5 | KLIC | +0.7% | %51 | ✅ |
| 6 | UCTT | +0.6% | %50 |  |
| 7 | ACMR | +0.6% | %50 |  |
| 8 | VECO | +0.6% | %50 |  |
| 9 | ICHR | +0.7% | %49 |  |
| 10 | FORM | +0.7% | %49 |  |

Geçmiş karne: 353 haftanın %54'inde seçilen hisseler kıyası (IWM) yendi; haftalık ortalama +0.4% (masraf öncesi). Tüm liste: `reports/smtk_peers_tahmin.csv`, hafta hafta geçmiş: `reports/smtk_peers_gecmis.csv`.
