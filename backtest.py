"""ETH backtest harness — AIProve eth-pnl-fixed bounty.

Stdlib-only, deterministic. Signals computed at bar close i are executed at
the OPEN of bar i+1 (no phantom fills).

COST MODEL (no explicit numbers exist in the public spec repo — grep of the
whole /tmp/aiprove-spec found only the README line "maker + taker fees,
slippage scaled by size"; the grader v1 code only implements forecast/Brier).
Assumptions, deliberately conservative (Binance spot standard tier, no VIP/BNB):
  * all orders are market (taker): 10 bps (0.10%) of notional traded
  * slippage: 2 bps base + 10 bps * |position fraction|  (scales with size)
  * round-trip cost at full size ≈ 2 * (10 + 12) = 44 bps
Capital: $10,000. Positions are a fraction of capital in [-1, +1] (long/short
allowed — spot-short via margin/perp is the standard reading of "positions";
a long-only variant is also reported). Mark-to-market on close.
"""
import csv, math, statistics, sys

CAPITAL = 10_000.0
TAKER_BPS = 10.0
SLIP_BASE_BPS = 2.0
SLIP_SIZE_BPS = 10.0


def load_bars(path="bars.csv"):
    rows = list(csv.DictReader(open(path)))
    return [dict(minute=int(r["minute"]), open=float(r["open"]),
                 high=float(r["high"]), low=float(r["low"]),
                 close=float(r["close"]), volume=float(r["volume"]))
            for r in rows]


def ema(series, n):
    k = 2.0 / (n + 1)
    out, e = [], None
    for x in series:
        e = x if e is None else x * k + e * (1 - k)
        out.append(e)
    return out


def sma(series, n):
    out = []
    for i in range(len(series)):
        w = series[max(0, i - n + 1):i + 1]
        out.append(sum(w) / len(w))
    return out


def backtest(bars, target_frac, start=0, end=None):
    """target_frac[i] in [-1,1]: desired position fraction decided at close i,
    executed at open of bar i+1. Returns metrics dict."""
    end = len(bars) if end is None else end
    closes = [b["close"] for b in bars]
    opens = [b["open"] for b in bars]
    equity = CAPITAL
    pos = 0.0            # fraction of capital currently held (signed, in ETH terms)
    entry_px = 0.0
    cash = CAPITAL       # cash after trades; equity = cash + pos*CAPITAL*px/entry_px ... track in units instead
    # Track in ETH units: holdings = pos_frac * CAPITAL / entry price
    units = 0.0
    cash = CAPITAL
    trades = 0
    round_trips = []     # (pnl incl. costs) per completed round trip
    open_pnl_cost = 0.0
    peak = CAPITAL
    max_dd = 0.0
    eq_curve = []
    last_dir = 0
    for i in range(start, end):
        # mark to market at close i
        eq = cash + units * closes[i]
        eq_curve.append(eq)
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
        if i + 1 >= end:
            break
        tgt = max(-1.0, min(1.0, target_frac[i]))
        delta = tgt - pos
        if abs(delta) < 1e-9:
            continue
        px = opens[i + 1]
        notional = abs(delta) * CAPITAL
        # execute at next open
        new_units = tgt * CAPITAL / px
        d_units = new_units - units
        cash -= d_units * px
        fee = notional * TAKER_BPS / 1e4
        slip = notional * (SLIP_BASE_BPS + SLIP_SIZE_BPS * abs(tgt)) / 1e4
        cash -= fee + slip
        trades += 1
        if (pos == 0.0 and tgt != 0.0):
            open_pnl_cost = fee + slip
            last_dir = 1 if tgt > 0 else -1
        elif tgt == 0.0 and pos != 0.0:
            # close of a round trip: pnl = equity change since open minus costs
            pass
        units = new_units
        pos = tgt
    # final mark
    eq = cash + units * closes[end - 1]
    eq_curve.append(eq)
    peak = max(peak, eq)
    max_dd = max(max_dd, peak - eq)
    return dict(net_pnl=eq - CAPITAL, final_equity=eq, trades=trades,
                max_dd=max_dd, max_dd_pct=100 * max_dd / CAPITAL,
                eq_curve=eq_curve)


def round_trip_stats(bars, target_frac, start=0, end=None):
    """Win rate over completed round trips (entry->flat), net of costs."""
    end = len(bars) if end is None else end
    closes = [b["close"] for b in bars]
    opens = [b["open"] for b in bars]
    cash, units, pos = CAPITAL, 0.0, 0.0
    trips, open_eq = [], None
    for i in range(start, end):
        if i + 1 >= end:
            break
        tgt = max(-1.0, min(1.0, target_frac[i]))
        delta = tgt - pos
        if abs(delta) < 1e-9:
            continue
        px = opens[i + 1]
        notional = abs(delta) * CAPITAL
        new_units = tgt * CAPITAL / px
        cash -= (new_units - units) * px
        cash -= notional * TAKER_BPS / 1e4
        cash -= notional * (SLIP_BASE_BPS + SLIP_SIZE_BPS * abs(tgt)) / 1e4
        if pos == 0.0 and tgt != 0.0:
            open_eq = cash + new_units * px
        elif tgt == 0.0 and pos != 0.0 and open_eq is not None:
            trips.append((cash + 0.0) - open_eq)  # cash now = value after close
            open_eq = None
        units, pos = new_units, tgt
    # close any open position at final close for trip accounting (mark only)
    if pos != 0.0 and open_eq is not None:
        trips.append((cash + units * closes[end - 1]) - open_eq)
    wins = sum(1 for t in trips if t > 0)
    return dict(n_trips=len(trips),
                win_rate=100.0 * wins / len(trips) if trips else 0.0,
                avg_trip=sum(trips) / len(trips) if trips else 0.0)


# ---------------- strategies: each returns target_frac list ----------------

def strat_ema_xover(bars, fast, slow, size=1.0, long_only=False):
    c = [b["close"] for b in bars]
    ef, es = ema(c, fast), ema(c, slow)
    out = []
    for i in range(len(bars)):
        if i < slow:
            out.append(0.0)
        elif ef[i] > es[i]:
            out.append(size)
        else:
            out.append(0.0 if long_only else -size)
    return out


def strat_bollinger_mr(bars, n, k_entry, k_exit, size=1.0, long_only=False):
    c = [b["close"] for b in bars]
    m = sma(c, n)
    out, pos = [], 0.0
    for i in range(len(bars)):
        if i < n:
            out.append(0.0)
            continue
        w = c[i - n + 1:i + 1]
        sd = statistics.pstdev(w)
        z = (c[i] - m[i]) / sd if sd > 0 else 0.0
        if pos == 0.0:
            if z < -k_entry:
                pos = size
            elif z > k_entry and not long_only:
                pos = -size
        elif pos > 0 and z > -k_exit:
            pos = 0.0
        elif pos < 0 and z < k_exit:
            pos = 0.0
        out.append(pos)
    return out


def strat_donchian(bars, n, size=1.0, long_only=False):
    c = [b["close"] for b in bars]
    h = [b["high"] for b in bars]
    l = [b["low"] for b in bars]
    out = []
    for i in range(len(bars)):
        if i < n:
            out.append(0.0)
            continue
        hh = max(h[i - n:i])
        ll = min(l[i - n:i])
        if c[i] > hh:
            out.append(size)
        elif c[i] < ll:
            out.append(0.0 if long_only else -size)
        else:
            out.append(out[-1] if out else 0.0)
    return out


def strat_rsi_mr(bars, n, lo, hi, size=1.0, long_only=False):
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
            elif rsi > hi and not long_only:
                pos = -size
        elif pos > 0 and rsi > 50:
            pos = 0.0
        elif pos < 0 and rsi < 50:
            pos = 0.0
        out.append(pos)
    return out


def strat_ema_filtered_mr(bars, fast, slow, n, k_entry, k_exit, size=1.0):
    """Mean-revert only in the direction of the EMA trend (short when price
    above trend-band, long when below) — hybrid."""
    c = [b["close"] for b in bars]
    ef, es = ema(c, fast), ema(c, slow)
    m = sma(c, n)
    out, pos = [], 0.0
    for i in range(len(bars)):
        if i < max(slow, n):
            out.append(0.0)
            continue
        w = c[i - n + 1:i + 1]
        sd = statistics.pstdev(w)
        z = (c[i] - m[i]) / sd if sd > 0 else 0.0
        trend_up = ef[i] > es[i]
        if pos == 0.0:
            if z < -k_entry and trend_up:
                pos = size
            elif z > k_entry and not trend_up:
                pos = -size
        elif pos > 0 and (z > -k_exit or not trend_up):
            pos = 0.0
        elif pos < 0 and (z < k_exit or trend_up):
            pos = 0.0
        out.append(pos)
    return out


def evaluate(name, bars, tgt, start=0, end=None):
    r = backtest(bars, tgt, start, end)
    rt = round_trip_stats(bars, tgt, start, end)
    r.update(rt)
    r["name"] = name
    return r


def show(r):
    print(f"{r['name']:55s} PnL ${r['net_pnl']:8.2f}  trades {r['trades']:4d}  "
          f"trips {r['n_trips']:3d} win {r['win_rate']:5.1f}%  maxDD ${r['max_dd']:7.2f} ({r['max_dd_pct']:.2f}%)")


if __name__ == "__main__":
    bars = load_bars(sys.argv[1] if len(sys.argv) > 1 else "bars.csv")
    N = len(bars)
    H = N // 2
    print(f"bars={N}  IS=0..{H-1}  OOS={H}..{N-1}  capital=${CAPITAL:,.0f}  "
          f"taker={TAKER_BPS}bps slip={SLIP_BASE_BPS}+{SLIP_SIZE_BPS}*|frac|bps")
    print("--- baselines (full sample) ---")
    show(evaluate("buy-and-hold", bars, [1.0] * N))
    show(evaluate("always short", bars, [-1.0] * N))
    print("--- EMA crossover grid (IS) ---")
    best = []
    for fast in (5, 10, 20):
        for slow in (20, 50, 100, 200):
            if fast >= slow:
                continue
            for size in (0.5, 1.0):
                for lo in (False, True):
                    r = evaluate(f"ema {fast}/{slow} size={size} long_only={lo}", bars,
                                 strat_ema_xover(bars, fast, slow, size, lo), 0, H)
                    best.append(r)
    best.sort(key=lambda r: r["net_pnl"], reverse=True)
    for r in best[:6]:
        show(r)
    print("--- Bollinger MR grid (IS) ---")
    bb = []
    for n in (10, 20, 30, 60):
        for ke in (1.0, 1.5, 2.0, 2.5):
            for kx in (0.0, 0.5):
                for size in (0.5, 1.0):
                    for lo in (False, True):
                        r = evaluate(f"boll n={n} ke={ke} kx={kx} size={size} lo={lo}", bars,
                                     strat_bollinger_mr(bars, n, ke, kx, size, lo), 0, H)
                        bb.append(r)
    bb.sort(key=lambda r: r["net_pnl"], reverse=True)
    for r in bb[:6]:
        show(r)
    print("--- Donchian / RSI grids (IS) ---")
    dd = []
    for n in (10, 20, 40, 60):
        for size in (0.5, 1.0):
            for lo in (False, True):
                r = evaluate(f"donchian n={n} size={size} lo={lo}", bars,
                             strat_donchian(bars, n, size, lo), 0, H)
                dd.append(r)
    for n in (7, 14, 21):
        for lo_t, hi_t in ((20, 80), (30, 70), (25, 75)):
            for size in (0.5, 1.0):
                r = evaluate(f"rsi n={n} {lo_t}/{hi_t} size={size}", bars,
                             strat_rsi_mr(bars, n, lo_t, hi_t, size), 0, H)
                dd.append(r)
    dd.sort(key=lambda r: r["net_pnl"], reverse=True)
    for r in dd[:6]:
        show(r)
    print("--- EMA-filtered MR grid (IS) ---")
    hy = []
    for fast, slow in ((10, 50), (20, 100)):
        for n in (20, 30):
            for ke in (1.5, 2.0):
                for kx in (0.0, 0.5):
                    r = evaluate(f"hyb ema{fast}/{slow} boll n={n} ke={ke} kx={kx}", bars,
                                 strat_ema_filtered_mr(bars, fast, slow, n, ke, kx), 0, H)
                    hy.append(r)
    hy.sort(key=lambda r: r["net_pnl"], reverse=True)
    for r in hy[:6]:
        show(r)
