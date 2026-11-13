"""OOS + fold validation for the top candidates from each family (IS grid),
plus regime-switch trend strategies. Pick by OOS, not IS."""
import sys
sys.path.insert(0, ".")
from backtest import *

bars = load_bars("bars.csv")
N = len(bars)
H = N // 2

cands = [
    ("RSI21 25/75 size1.0", strat_rsi_mr(bars, 21, 25, 75, 1.0)),
    ("RSI21 20/80 size1.0", strat_rsi_mr(bars, 21, 20, 80, 1.0)),
    ("RSI21 30/70 size0.5", strat_rsi_mr(bars, 21, 30, 70, 0.5)),
    ("RSI14 25/75 size1.0", strat_rsi_mr(bars, 14, 25, 75, 1.0)),
    ("RSI14 30/70 size1.0", strat_rsi_mr(bars, 14, 30, 70, 1.0)),
    ("Boll10 2.5/0.5 size0.5 LO", strat_bollinger_mr(bars, 10, 2.5, 0.5, 0.5, True)),
    ("Boll60 2.5/0.5 size0.5 LO", strat_bollinger_mr(bars, 60, 2.5, 0.5, 0.5, True)),
    ("EMA20/100 size0.5 LO", strat_ema_xover(bars, 20, 100, 0.5, True)),
    ("EMA10/200 size0.5 LO", strat_ema_xover(bars, 10, 200, 0.5, True)),
    ("EMA20/100 size1.0", strat_ema_xover(bars, 20, 100, 1.0, False)),
    ("EMA10/50 size1.0", strat_ema_xover(bars, 10, 50, 1.0, False)),
    ("EMA5/20 size1.0", strat_ema_xover(bars, 5, 20, 1.0, False)),
    ("Donch20 size1.0", strat_donchian(bars, 20, 1.0, False)),
    ("Donch40 size1.0", strat_donchian(bars, 40, 1.0, False)),
]

def regime(bars, n, size=1.0, long_only=False):
    """Position = +size if close > EMA(n) else -size (or 0 if long-only)."""
    c = [b["close"] for b in bars]
    e = ema(c, n)
    out = []
    for i in range(len(bars)):
        if i < n:
            out.append(0.0)
        elif c[i] > e[i]:
            out.append(size)
        else:
            out.append(0.0 if long_only else -size)
    return out

for n in (50, 100, 200):
    for size in (0.5, 1.0):
        cands.append((f"RegimeEMA{n} size{size}", regime(bars, n, size)))
        cands.append((f"RegimeEMA{n} size{size} LO", regime(bars, n, size, True)))

print("=== OOS (bars 720-1439) — ranked by OOS PnL ===")
rows = []
for name, tgt in cands:
    r_is = evaluate(name, bars, tgt, 0, H)
    r_oos = evaluate(name, bars, tgt, H, N)
    r_full = evaluate(name, bars, tgt, 0, N)
    rows.append((r_oos["net_pnl"], name, r_is, r_oos, r_full))
rows.sort(key=lambda x: -x[0])
for _, name, ri, ro, rf in rows:
    print(f"{name:28s} IS ${ri['net_pnl']:8.2f} (tr {ri['trades']:3d}) | "
          f"OOS ${ro['net_pnl']:8.2f} (tr {ro['trades']:3d} win {ro['win_rate']:.0f}% DD ${ro['max_dd']:.2f}) | "
          f"FULL ${rf['net_pnl']:8.2f} (tr {rf['trades']:3d} DD ${rf['max_dd']:.2f})")

print("\n=== 4-fold (360-bar) PnL for top-5 OOS ===")
tgt_by_name = {n: t for n, t in cands}
for _, name, ri, ro, rf in rows[:5]:
    folds = []
    for f in range(4):
        r = evaluate(name, bars, tgt_by_name[name], f * 360, (f + 1) * 360)
        folds.append(r["net_pnl"])
    print(f"{name:28s} folds " + " ".join(f"${x:7.2f}" for x in folds))
