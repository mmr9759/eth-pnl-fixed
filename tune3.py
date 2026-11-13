"""Round 3: hybrids (RSI entries + EMA trend filter) + fee sensitivity for the
leading candidates. Decide by OOS + consistency, not by a single number."""
import sys
sys.path.insert(0, ".")
import backtest as bt
from backtest import *

bars = load_bars("bars.csv")
N = len(bars)
H = N // 2


def strat_rsi_trend(bars, n, lo, hi, ema_n, size=1.0):
    """RSI mean-reversion entries, but only in the direction of the EMA trend
    (short only when close < EMA, long only when close > EMA). Exit at 50."""
    c = [b["close"] for b in bars]
    e = ema(c, ema_n)
    gains, losses = [0.0], [0.0]
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    out, pos = [], 0.0
    for i in range(len(bars)):
        if i < max(n, ema_n):
            out.append(0.0)
            continue
        ag = sum(gains[i - n + 1:i + 1]) / n
        al = sum(losses[i - n + 1:i + 1]) / n
        rsi = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        trend_up = c[i] > e[i]
        if pos == 0.0:
            if rsi < lo and trend_up:
                pos = size
            elif rsi > hi and not trend_up:
                pos = -size
        elif pos > 0 and rsi > 50:
            pos = 0.0
        elif pos < 0 and rsi < 50:
            pos = 0.0
        out.append(pos)
    return out


def strat_rsi_exit(bars, n, lo, hi, exit_lo, exit_hi, size=1.0):
    c = [b["close"] for b in bars]
    gains, losses = [0.0], [0.0]
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    out, pos = [], 0.0
    for i in range(len(bars)):
        if i < n:
            out.append(0.0)
            continue
        ag = sum(gains[i - n + 1:i + 1]) / n
        al = sum(losses[i - n + 1:i + 1]) / n
        rsi = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        if pos == 0.0:
            if rsi < lo:
                pos = size
            elif rsi > hi:
                pos = -size
        elif pos > 0 and rsi > exit_hi:
            pos = 0.0
        elif pos < 0 and rsi < exit_lo:
            pos = 0.0
        out.append(pos)
    return out


def strat_hour_momentum(bars, lookback, thresh, hold_min, size=1.0):
    c = [b["close"] for b in bars]
    out, pos, held = [], 0.0, 0
    for i in range(len(bars)):
        if i < lookback:
            out.append(0.0)
            continue
        r = c[i] / c[i - lookback] - 1
        held += 1
        if pos == 0.0:
            if r < -thresh:
                pos, held = -size, 0
            elif r > thresh:
                pos, held = size, 0
        elif pos < 0 and (r > 0 or held >= hold_min):
            pos, held = 0.0, 0
        elif pos > 0 and (r < 0 or held >= hold_min):
            pos, held = 0.0, 0
        out.append(pos)
    return out


print("=== RSI + trend filter (IS) ===")
for ema_n in (100, 200):
    for n, lo_t, hi_t in ((21, 20, 80), (21, 25, 75), (28, 20, 80)):
        r = evaluate(f"rsiT n={n} {lo_t}/{hi_t} ema{ema_n}", bars,
                     strat_rsi_trend(bars, n, lo_t, hi_t, ema_n), 0, H)
        show(r)
print("=== RSI exit variants (IS) ===")
for ex_lo, ex_hi in ((40, 60), (45, 55), (50, 50)):
    r = evaluate(f"rsi21 20/80 exit {ex_lo}/{ex_hi}", bars,
                 strat_rsi_exit(bars, 21, 20, 80, ex_lo, ex_hi), 0, H)
    show(r)

print("\n=== OOS/FULL/folds for hybrids ===")
hyb = [
    ("rsiT21 20/80 ema200", strat_rsi_trend(bars, 21, 20, 80, 200)),
    ("rsiT21 25/75 ema200", strat_rsi_trend(bars, 21, 25, 75, 200)),
    ("rsiT21 20/80 ema100", strat_rsi_trend(bars, 21, 20, 80, 100)),
    ("rsi21 20/80 exit40/60", strat_rsi_exit(bars, 21, 20, 80, 40, 60)),
]
for name, tgt in hyb:
    ri = evaluate(name, bars, tgt, 0, H)
    ro = evaluate(name, bars, tgt, H, N)
    rf = evaluate(name, bars, tgt, 0, N)
    folds = [evaluate(name, bars, tgt, f * 360, (f + 1) * 360)["net_pnl"] for f in range(4)]
    print(f"{name:28s} IS ${ri['net_pnl']:8.2f} | OOS ${ro['net_pnl']:8.2f} (tr {ro['trades']:2d}) | "
          f"FULL ${rf['net_pnl']:8.2f} (tr {rf['trades']:2d} DD ${rf['max_dd']:6.2f}) | folds " +
          " ".join(f"${x:7.2f}" for x in folds))

print("\n=== Fee sensitivity (FULL sample) ===")
print("scenarios: (taker bps, slip base bps, slip size bps)")
import importlib
import backtest as btmod


def strat_dbema200(bars):
    c = [b["close"] for b in bars]
    e = ema(c, 200)
    out, pos = [], 0.0
    for i in range(len(bars)):
        if i < 200:
            out.append(0.0)
            continue
        if c[i] > e[i] * 1.01:
            pos = 1.0
        elif c[i] < e[i] * 0.99:
            pos = -1.0
        out.append(pos)
    return out


leaders = [
    ("dbEMA200 band0.01 size1.0", strat_dbema200(bars)),
    ("rsi21 20/80 size1.0", strat_rsi_mr(bars, 21, 20, 80, 1.0)),
    ("rsiT21 20/80 ema200", strat_rsi_trend(bars, 21, 20, 80, 200)),
    ("boll20 k3 kx0.5 size0.5", strat_bollinger_mr(bars, 20, 3.0, 0.5, 0.5)),
    ("hmom120 th0.008 hold120 s0.5", strat_hour_momentum(bars, 120, 0.008, 120, 0.5)),
]
for taker, sb, ss in ((0, 0, 0), (5, 2, 10), (10, 2, 10), (10, 5, 20), (15, 2, 10)):
    btmod.TAKER_BPS, btmod.SLIP_BASE_BPS, btmod.SLIP_SIZE_BPS = taker, sb, ss
    line = f"fee taker={taker:2d} slip={sb}+{ss}: "
    for name, tgt in leaders:
        r = evaluate(name, bars, tgt, 0, N)
        line += f"{name[:12]} ${r['net_pnl']:7.2f}  "
    print(line)
btmod.TAKER_BPS, btmod.SLIP_BASE_BPS, btmod.SLIP_SIZE_BPS = 10.0, 2.0, 10.0
