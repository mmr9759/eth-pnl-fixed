"""Round 2: low-trade-count strategies targeting multi-hour legs.
Tune on IS (bars 0-719), validate on OOS (720-1439) + 4 folds."""
import sys
sys.path.insert(0, ".")
from backtest import *

bars = load_bars("bars.csv")
N = len(bars)
H = N // 2
closes = [b["close"] for b in bars]


def strat_deadband_ema(bars, n, band, size=1.0, long_only=False):
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
            pos = 0.0 if long_only else -size
        out.append(pos)
    return out


def strat_hour_momentum(bars, lookback, thresh, hold_min, size=1.0):
    """Short when trailing `lookback`-bar return < -thresh, long when > +thresh.
    Exit when the return reverses sign past 0, or after hold_min bars."""
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


def strat_trail_momentum(bars, lookback, thresh, trail, size=1.0):
    """Enter on trailing-return momentum; exit on `trail` retracement from the
    best price since entry (trailing stop), or on momentum reversal."""
    c = [b["close"] for b in bars]
    out, pos = [], 0.0
    best = None
    for i in range(len(bars)):
        if i < lookback:
            out.append(0.0)
            continue
        r = c[i] / c[i - lookback] - 1
        if pos == 0.0:
            if r < -thresh:
                pos, best = -size, c[i]
            elif r > thresh:
                pos, best = size, c[i]
        elif pos < 0:
            best = min(best, c[i])
            if c[i] > best * (1 + trail) or r > 0:
                pos, best = 0.0, None
        elif pos > 0:
            best = max(best, c[i])
            if c[i] < best * (1 - trail) or r < 0:
                pos, best = 0.0, None
        out.append(pos)
    return out


results = []

print("=== deadband EMA (IS grid) ===")
db = []
for n in (50, 100, 200):
    for band in (0.002, 0.005, 0.01):
        for size in (0.5, 1.0):
            for lo in (False, True):
                r = evaluate(f"dbEMA{n} band={band} size={size} lo={lo}", bars,
                             strat_deadband_ema(bars, n, band, size, lo), 0, H)
                db.append(r)
db.sort(key=lambda r: r["net_pnl"], reverse=True)
for r in db[:5]:
    show(r)
results += db[:5]

print("=== hour momentum (IS grid) ===")
hm = []
for lb in (30, 60, 120):
    for th in (0.005, 0.008, 0.012):
        for hold in (60, 120, 240):
            for size in (0.5, 1.0):
                r = evaluate(f"hmom lb={lb} th={th} hold={hold} size={size}", bars,
                             strat_hour_momentum(bars, lb, th, hold, size), 0, H)
                hm.append(r)
hm.sort(key=lambda r: r["net_pnl"], reverse=True)
for r in hm[:5]:
    show(r)
results += hm[:5]

print("=== trailing momentum (IS grid) ===")
tm = []
for lb in (30, 60, 120):
    for th in (0.005, 0.008, 0.012):
        for tr in (0.003, 0.005, 0.01):
            for size in (0.5, 1.0):
                r = evaluate(f"tmom lb={lb} th={th} trail={tr} size={size}", bars,
                             strat_trail_momentum(bars, lb, th, tr, size), 0, H)
                tm.append(r)
tm.sort(key=lambda r: r["net_pnl"], reverse=True)
for r in tm[:5]:
    show(r)
results += tm[:5]

print("=== RSI extreme grid (IS) ===")
rs = []
for n in (14, 21, 28):
    for lo_t, hi_t in ((15, 85), (20, 80), (25, 75)):
        for size in (0.75, 1.0):
            r = evaluate(f"rsi n={n} {lo_t}/{hi_t} size={size}", bars,
                         strat_rsi_mr(bars, n, lo_t, hi_t, size), 0, H)
            rs.append(r)
rs.sort(key=lambda r: r["net_pnl"], reverse=True)
for r in rs[:5]:
    show(r)
results += rs[:5]

print("=== Bollinger k=3 grid (IS) ===")
bl = []
for n in (20, 30, 60):
    for kx in (0.0, 0.5, 1.0):
        for size in (0.5, 1.0):
            r = evaluate(f"boll n={n} ke=3.0 kx={kx} size={size}", bars,
                         strat_bollinger_mr(bars, n, 3.0, kx, size), 0, H)
            bl.append(r)
bl.sort(key=lambda r: r["net_pnl"], reverse=True)
for r in bl[:5]:
    show(r)
results += bl[:5]

print("\n=== OOS + FULL + folds for all IS-top candidates ===")
seen = set()
for r in results:
    if r["name"] in seen:
        continue
    seen.add(r["name"])
# rebuild targets by name
all_tgt = {}
for n in (50, 100, 200):
    for band in (0.002, 0.005, 0.01):
        for size in (0.5, 1.0):
            for lo in (False, True):
                all_tgt[f"dbEMA{n} band={band} size={size} lo={lo}"] = strat_deadband_ema(bars, n, band, size, lo)
for lb in (30, 60, 120):
    for th in (0.005, 0.008, 0.012):
        for hold in (60, 120, 240):
            for size in (0.5, 1.0):
                all_tgt[f"hmom lb={lb} th={th} hold={hold} size={size}"] = strat_hour_momentum(bars, lb, th, hold, size)
for lb in (30, 60, 120):
    for th in (0.005, 0.008, 0.012):
        for tr in (0.003, 0.005, 0.01):
            for size in (0.5, 1.0):
                all_tgt[f"tmom lb={lb} th={th} trail={tr} size={size}"] = strat_trail_momentum(bars, lb, th, tr, size)
for n in (14, 21, 28):
    for lo_t, hi_t in ((15, 85), (20, 80), (25, 75)):
        for size in (0.75, 1.0):
            all_tgt[f"rsi n={n} {lo_t}/{hi_t} size={size}"] = strat_rsi_mr(bars, n, lo_t, hi_t, size)
for n in (20, 30, 60):
    for kx in (0.0, 0.5, 1.0):
        for size in (0.5, 1.0):
            all_tgt[f"boll n={n} ke=3.0 kx={kx} size={size}"] = strat_bollinger_mr(bars, n, 3.0, kx, size)

rows = []
for r in results:
    if r["name"] in seen and r["name"] in all_tgt:
        pass
    name = r["name"]
    if name not in all_tgt:
        continue
    tgt = all_tgt[name]
    ro = evaluate(name, bars, tgt, H, N)
    rf = evaluate(name, bars, tgt, 0, N)
    folds = [evaluate(name, bars, tgt, f * 360, (f + 1) * 360)["net_pnl"] for f in range(4)]
    rows.append((ro["net_pnl"], name, r, ro, rf, folds))
rows.sort(key=lambda x: -x[0])
for _, name, ri, ro, rf, folds in rows:
    print(f"{name:42s} IS ${ri['net_pnl']:8.2f} | OOS ${ro['net_pnl']:8.2f} (tr {ro['trades']:2d} win {ro['win_rate']:.0f}% DD ${ro['max_dd']:6.2f}) | "
          f"FULL ${rf['net_pnl']:8.2f} (tr {rf['trades']:2d} DD ${rf['max_dd']:6.2f}) | folds " +
          " ".join(f"${x:7.2f}" for x in folds))
