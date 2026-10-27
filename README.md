# market-data

Bu dal GitHub Actions tarafından otomatik yazılır; elle düzenlemeyin.

- `daily/<kaynak>/<SEMBOL>.csv`: günlük fiyatlar (her iş günü kapanıştan sonra eklenir)
- `reports/<isim>.json`: haftalık walk-forward araştırma raporları

Bu bir analizdir; buradaki hiçbir şey emir ya da yatırım tavsiyesi değildir.

## Durum
Son çalışma: **Haftalık araştırma**, 2026-10-27 20:30 UTC

### Veri
| Kaynak | Hisse | En güncel gün | En geride kalan |
|---|---|---|---|
| yahoo_bist | 30 | 2026-10-23 | hepsi güncel |
| yahoo_us | 31 | 2026-10-23 | SKYT (2026-07-30) |

### Haftalık araştırma
| Rapor | Tür | Tarih | Model | IC t | Toplam (model) | Seçilen strateji → gelecek hafta |
|---|---|---|---|---|---|---|
| bist_likit | sıralama (25/44 elemeden geçti) | 2026-10-27 | FAIL ❌ | 0.60 | +95.3% | **near_high_12w** [ORTA]: GARAN, YKBNK, SAHOL, TUPRS, KCHOL |
| smtk_peers | sıralama (14/30 elemeden geçti) | 2026-10-27 | FAIL ❌ | -0.71 | -63.3% | **low_vol_12w** [ZAYIF]: PLAB, AMBA, LASR, KLIC, UCTT |
| smtk_timeseries | tek hisse | 2026-10-27 | FAIL ❌ | -0.50 | -46.2% | SMTK FLAT _(model FAIL: sinyal değil)_ |
