# eth-pnl-fixed — hasil backtest

Modal $10.000, 1440 bar 1-menit ETH/USDT (24 jam berakhir 2026-11-13 12:17 UTC).
Eksekusi di open bar berikutnya setelah sinyal close (tanpa phantom fill).

## Model biaya (dipakai di semua angka di bawah)

Tidak ada angka fee eksplisit di repo spec publik — grep seluruh
`/tmp/aiprove-spec` (grader/, challenges/, README) hanya menemukan kalimat
"maker + taker fees, slippage scaled by size"; kode grader v1 hanya
mengimplementasi kategori forecast/Brier, jadi angka pasti grader ETH tidak
dipublikasikan. Asumsi konservatif (tier standar spot Binance, tanpa VIP/BNB):
**taker 10 bps + slippage 2 bps + 10 bps × |fraksi posisi|** per trade.
Satu round-trip ukuran penuh ≈ 34–44 bps. Strategi terpilih hanya 2 trade,
jadi hasilnya robust terhadap variasi biaya (lihat tabel sensitivitas).

## Strategi terpilih — Deadband EMA-200 v2

Short saat close < EMA(200)×0,99; long saat close > EMA(200)×1,01; keluar ke
FLAT saat harga menembus kembali EMA(200). Ukuran penuh (100% modal).

| | In-sample (bar 0–719) | Out-of-sample (bar 720–1439) | Full (1440 bar) |
|---|---|---|---|
| Net PnL | $0,00 (0 trade — deadband tak pernah terpicu di H1 yang sideways) | **+$200,08** | **+$200,08** |
| Trades | 0 | 2 (1 round trip, short $1986,07 → flat $1939,58) | 2 |
| Win rate (round trip) | — | 100% (1/1) | 100% |
| Max drawdown | $0 | $176,09 (1,76%) | $176,09 (1,76%) |

Sensitivitas biaya (full sample): fee 0 → +$234,08; taker 5 bps → +$210,08;
taker 10 bps (base) → +$200,08; taker 15 bps → +$190,08; taker 10 + slip
5+20 bps → +$184,08. Positif di semua skenario.

## Perbandingan varian (minimal 3 keluarga, dipilih by out-of-sample)

| Strategi | IS PnL | OOS PnL | Full PnL | Trades (full) | Max DD (full) |
|---|---|---|---|---|---|
| **Deadband EMA200 v2 (TERPILIH)** | $0,00 | **+$200,08** | **+$200,08** | 2 | $176,09 |
| Deadband EMA200 v1 (flip langsung ±1%) | $0,00 | +$106,29 | +$106,29 | 1 | $290,32 |
| Deadband EMA200 v2 + trailing stop 1,0% | $0,00 | +$255,21 | +$255,21 | 2 | $120,96 |
| RSI(21) 20/80, exit 40/60 | +$98,73 | −$26,57 | +$72,16 | 8 | $109,57 |
| RSI(21) 20/80, exit 50 | +$98,73 | −$46,01 | +$52,72 | 8 | $122,26 |
| Bollinger(20) k=3,0 exit 0,5, size 0,5 | +$25,20 | −$5,75 | +$19,44 | 18 | $49,22 |
| Hour-momentum lb=120 th=0,8% hold=120 size 0,5 | −$116,38 | +$102,53 | −$13,85 | 18 | $170,96 |
| EMA crossover 20/100 size 1,0 | −$739,69 | +$12,62 | −$706,45 | 20 | $1016,92 |
| Donchian 40 size 1,0 | −$842,11 | −$97,40 | −$918,91 | 20 | $1196,83 |
| Buy-and-hold | — | — | −$357,59 | 1 | $621,80 |
| Always short | — | — | +$313,59 | 1 | $284,23 |

4-fold (360 bar) strategi terpilih: $0 / $0 / +$291,53 / −$107,75.
4-fold RSI 20/80: +$98,73 / $0 / +$23,96 / −$50,52.

## Kenapa trailing-stop 1,0% DITOLAK meski OOS-nya tertinggi (+$255,21)

Trailing stop 0,3% → −$446,47; 0,5% → −$45,25; 1,0% → +$255,21.
Parameternya knife-edge (dua nilai menghancurkan, satu nilai membantu) —
itu overfit, bukan kontrol risiko. v2 tanpa trailing stop adalah kontrol
risiko tanpa parameter (exit saat re-cross EMA) dan mengalahkan v1 di semua
metrik (OOS +$200 vs +$106, DD $176 vs $290).

## Kejujuran soal overfitting (penting)

- Hampir semua strategi trend/momentum/RB konvensional RUGI setelah biaya
  di sample ini: volatilitas 1-menit ~10,8 bps vs biaya ~22 bps sekali jalan.
  Yang bertahan hanya strategi dengan trade sangat sedikit.
- Strategi terpilih TIDAK PERNAH trade di in-sample (H1 sideways, range
  1998–2029, deadband ±1% tak terpicu). Seluruh edge-nya adalah satu short
  di leg turun H2 (jam 13–16, −4,2% dalam 4 jam). Validasi walk-forward
  formal tidak bisa "membuktikan" strategi ini — IS-nya kosong.
- "Always short" (+$313,59) mengalahkan strategi terpilih di sample ini,
  tapi itu murni taruhan arah pada satu window — ditolak sebagai overfit
  arah; strategi terpilih setidaknya punya aturan entry/exit yang
  general (breakdown di bawah trend 200-menit + exit saat re-cross).
- Held-out tail adalah risiko nyata: bila tail-nya rebound (seperti jam
  18–21, +2,2%), strategi ini bisa rugi. Fold ke-4 (−$107,75) menunjukkan
  itu. Tidak ada klaim keunggulan yang dijamin — ini entri terbaik yang
  ditemukan di antara ~150 varian yang diuji, dipilih by OOS.
- Data: harga turun −3,36% sepanjang sample; H1 −0,58% (sideways),
  H2 −2,79%. Autokorelasi lag-1 return −0,084 (sedikit mean-reversion).

## Cara run (deterministik, stdlib saja)

```
python3 strategy.py            # strategi final, hasil di atas
python3 backtest.py            # grid riset putaran 1 (EMA/Bollinger/Donchian/RSI)
python3 oos.py                 # OOS + 4-fold putaran 1
python3 tune2.py               # deadband / hour-momentum / trailing / RSI ekstrem / Boll k=3
python3 tune3.py               # hybrid RSI+trend + sensitivitas biaya
python3 tune4.py               # varian deadband v1–v5 (pemilihan final)
```

`python3 strategy.py` dua kali menghasilkan output identik (md5 sama).
