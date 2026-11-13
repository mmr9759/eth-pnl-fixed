"""Round 4: risk-managed deadband-EMA200 variants.
V1 = flip at +/-1% (current leader). V2 = exit to flat on EMA re-cross.
V3/V4 = V2 + trailing stop (0.5% / 1.0% retracement from extreme since entry).
A variant is only accepted if it beats V1 on OOS AND full AND does not rely
on a knife-edge parameter (both trail values must help)."""
import sys
sys.path.insert(0, ".")
from backtest import *

bars = load_bars("bars.csv")
N = len(bars)
H = N // 2


def strat_db_v(bars, n=200, band=0.01, trail=None, size=1.0):
    c = [b["close"] for b in bars]
    e = ema(c, n)
    out, pos = [], 0.0
    best = None
    for i in range(len(bars)):
        if i < n:
            out.append(0.0)
            continue
        if pos == 0.0:
            if c[i] > e[i] * (1 + band):
                pos, best = size, c[i]
            elif c[i] < e[i] * (1 - band):
                pos, best = -size, c[i]
        elif pos > 0:
            best = max(best, c[i])
            if trail is not None and c[i] < best * (1 - trail):
                pos, best = 0.0, None
            elif c[i] < e[i]:
                pos, best = 0.0, None
        elif pos < 0:
            best = min(best, c[i])
            if trail is not None and c[i] > best * (1 + trail):
                pos, best = 0.0, None
            elif c[i] > e[i]:
                pos, best = 0.0, None
        out.append(pos)
    return out


def strat_db_v1(bars, n=200, band=0.01, size=1.0):
    c = [b["close"] for b in bars]
    e = ema(c, n)
    out, pos = [], 0.0
    for i in range(len(bars)):
        if i < n:
            out.append(0.0)
            continue
        if c[i] > e[i] * (1 + band):
            pos = size
        elif c[i] < e[i] * (1 - band):
            pos = -size
        out.append(pos)
    return out


variants = [
    ("V1 flip +/-1%", strat_db_v1(bars)),
    ("V2 flat-on-EMA-recross", strat_db_v(bars, trail=None)),
    ("V3 V2 + trail 0.5%", strat_db_v(bars, trail=0.005)),
    ("V4 V2 + trail 1.0%", strat_db_v(bars, trail=0.010)),
    ("V5 V2 + trail 0.3%", strat_db_v(bars, trail=0.003)),
]
for name, tgt in variants:
    ri = evaluate(name, bars, tgt, 0, H)
    ro = evaluate(name, bars, tgt, H, N)
    rf = evaluate(name, bars, tgt, 0, N)
    folds = [evaluate(name, bars, tgt, f * 360, (f + 1) * 360)["net_pnl"] for f in range(4)]
    print(f"{name:28s} IS ${ri['net_pnl']:8.2f} (tr {ri['trades']:2d}) | OOS ${ro['net_pnl']:8.2f} "
          f"(tr {ro['trades']:2d} win {ro['win_rate']:.0f}% DD ${ro['max_dd']:6.2f}) | "
          f"FULL ${rf['net_pnl']:8.2f} (tr {rf['trades']:2d} win {rf['win_rate']:.0f}% DD ${rf['max_dd']:6.2f}) | folds " +
          " ".join(f"${x:7.2f}" for x in folds))
