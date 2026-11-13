# eth-pnl-fixed — AIProve bounty

Highest backtest PnL on the fixed ETH dataset. Hadiah 2.000.000 PROVE.
Tutup ~7 hari dari 14 Nov 2026 01:25 WIB.

## Strategi

**Deadband EMA-200 v2** (`strategy.py`, Python stdlib saja):

- Short saat close < EMA(200) × 0,99; long saat close > EMA(200) × 1,01.
- Keluar ke FLAT saat harga menembus kembali EMA(200) (tanpa flip langsung).
- Ukuran penuh (100% dari modal $10.000), long/short diizinkan.
- Sinyal dihitung di close bar i, dieksekusi di OPEN bar i+1 (tanpa phantom fill).

## Hasil (modal $10.000, 1440 bar)

| | In-sample (bar 0–719) | Out-of-sample (bar 720–1439) | Full |
|---|---|---|---|
| Net PnL | $0,00 (0 trade) | **+$200,08** | **+$200,08** |
| Trades | 0 | 2 (1 round trip) | 2 |
| Max drawdown | — | $176,09 (1,76%) | $176,09 (1,76%) |

Satu-satunya trade: short $1986,07 (open bar 867) → flat $1939,58 (open bar 1094).

## Asumsi biaya

Tidak ada angka fee eksplisit di repo spec publik (grep seluruh
`/tmp/aiprove-spec` hanya menemukan "maker + taker fees, slippage scaled by
size"; grader v1 hanya mengimplementasi forecast/Brier). Dipakai asumsi
konservatif tier standar spot Binance: **taker 10 bps + slippage 2 bps +
10 bps × |fraksi posisi|** per trade. Strategi tetap positif (+$184 s.d.
+$234) di semua skenario biaya yang diuji, dari fee 0 sampai taker 15 bps.

## File

- `strategy.py` — strategi final + backtest harness (deterministik).
- `backtest.py`, `oos.py`, `tune2.py`, `tune3.py`, `tune4.py` — riset:
  grid EMA/Bollinger/Donchian/RSI, validasi OOS + 4-fold, sensitivitas biaya,
  dan pemilihan varian final. ~150 varian diuji; detail di `RESULTS.md`.
- `bars.csv` — dataset frozen dari spec (1440 bar 1-menit ETH/USDT Binance).
- `RESULTS.md` — hasil lengkap, perbandingan varian, dan kejujuran soal
  risiko overfitting (strategi tidak pernah trade di in-sample; seluruh
  edge dari satu short di leg turun H2; held-out tail bisa membaliknya).

## Cara run

```
python3 strategy.py
```

Output harus: `NET PnL: $200.08  trades: 2  max drawdown: $176.09 (1.76%)`.
Deterministik — dua run menghasilkan output identik.
