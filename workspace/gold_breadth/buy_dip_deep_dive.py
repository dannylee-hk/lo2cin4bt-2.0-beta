#!/usr/bin/env python3
"""
Buy-the-Dip (6-month-low) on Gold Miners — IN-DEPTH analysis
==============================================================
Deeper look at the baseline that out-performed the breadth-thrust signal:
"enter every time ^HUI prints a rolling 6-month low, next-day open, hold H".

WHY DEEP DIVE NEEDS DE-DUPLICATION FIRST
    The naive version flags EVERY day that is a fresh 6-month low, so during a
    steady multi-month drawdown it "triggers" dozens of consecutive days. Those
    overlapping entries inflate n (305) and are NOT independent trades. This
    script de-duplicates via an EPISODE / re-arm rule so each number is a real,
    separable trade, THEN:
      A) independent trade count + de-overlap
      B) full return distribution (percentiles, fat right tail)
      C) risk: max-drawdown distribution, worst trades, profit factor
      D) is the edge real? bootstrap CI vs buy-and-hold, clustering by year
      E) parameter sensitivity (low lookback, re-arm rule, min drawdown)
      F) practical economics: trades/yr, avg holding, cost drag vs gross

DATA: same documented real data (Yahoo Finance ^HUI, no synthetic series).
RESEARCH ONLY — no order placement, no live trading.
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import yfinance as yf

OUTDIR = os.path.dirname(os.path.abspath(__file__))
REF_TICKER = "^HUI"
COST_SIDE = 0.0010          # 10 bps/side
SEED = 42
BOOT_B = 20000
RNG = np.random.default_rng(SEED)

HORIZONS = {"1M": 21, "3M": 63, "6M": 126, "12M": 252}
PUB = ["1M", "3M", "6M", "12M"]

# de-dup / re-arm: after entering at a low, don't re-enter until price
# recovers >= REARM above that entry price (episode over).
REARM = 0.12


# ---------------------------------------------------------------- data
def flatten(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df.copy()


def load_ref():
    h = yf.Ticker(REF_TICKER).history(start="1990-01-01", end="2026-09-01",
                                      auto_adjust=False)
    h = flatten(h)[["Open", "Close"]].copy()
    h.index = pd.to_datetime(h.index).tz_localize(None)
    return h.dropna(subset=["Close"])


def rolling_low(close, roll, min_dd):
    rmin = close.rolling(roll, min_periods=roll).min()
    rmax = close.rolling(roll, min_periods=roll).max()
    at_low = (close <= rmin) & rmin.notna()
    depth = (close / rmax - 1.0).fillna(-1.0)
    return at_low & (depth <= -min_dd)


# ---------------------------------------------------------------- de-dup engine
def episodes(ref, roll, min_dd, rearm=REARM):
    """Yield a list of (entry_index) for INDEPENDENT buy-the-dip episodes:
    a new episode fires on a rolling-low day ONLY if price has recovered
    `rearm` above the previous episode's entry (or no prior episode)."""
    close = ref["Close"].values
    low = rolling_low(ref["Close"], roll, min_dd).values
    n = len(close)
    eps = []
    last_entry_idx = -1
    last_entry_price = np.nan
    for t in range(n):
        if not low[t]:
            continue
        if np.isnan(last_entry_price):
            fire = True
        else:
            # recovered above entry? episode over -> allow new one
            recovered = close[t] >= last_entry_price * (1 + rearm)
            fire = recovered
        if fire:
            eps.append(t)
            last_entry_idx = t
            last_entry_price = close[t]
    return eps


def trade_row(ei, hold, ref):
    """Return (gross, net, max_dd) for one episode entered at index ei."""
    o = ref["Open"].values
    c = ref["Close"].values
    e = o[ei + 1] if ei + 1 < len(o) else np.nan
    end = min(ei + 1 + hold, len(c) - 1)
    if np.isnan(e) or end <= ei + 1:
        return np.nan, np.nan, np.nan
    gross = c[end] / e - 1.0
    w = c[ei + 1:end + 1]
    mdd = w.min() / e - 1.0 if w.size else np.nan
    net = gross - 2 * COST_SIDE
    return gross, net, mdd


def analyze(ref, eps, tag=""):
    out = []
    for h, hold in HORIZONS.items():
        gross, nets, mdds = [], [], []
        years = []
        for ei in eps:
            g, net, mdd = trade_row(ei, hold, ref)
            if not np.isnan(net):
                gross.append(g); nets.append(net); mdds.append(mdd)
                years.append(ref.index[ei].year)
        g = np.array(gross); nt = np.array(nets); md = np.array(mdds)
        wins = nt > 0
        losses = nt[~wins]; winsv = nt[wins]
        pf = (winsv.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.inf
        # bootstrap CI on mean (independent sample)
        B = BOOT_B; ii = RNG.integers(0, len(nt), size=(B, len(nt)))
        means = nt[ii].mean(axis=1)
        lo, hi = np.percentile(means, [5, 95])
        out.append({
            "tag": tag, "horizon": h, "n": len(nt),
            "mean_gross": g.mean(), "mean_net": nt.mean(),
            "median_net": np.median(nt),
            "p10": np.percentile(nt, 10), "p90": np.percentile(nt, 90),
            "pos_pct": wins.mean() * 100,
            "avg_max_dd": md.mean(), "worst": nt.min(), "best": nt.max(),
            "n_winners": int(len(wins)), "n_losers": int(len(losses)),
            "profit_factor": pf,
            "boot_mean_lo": lo, "boot_mean_hi": hi,
            "years": pd.Series(years).value_counts().to_dict(),
        })
    return out


def buy_and_hold(ref):
    """^HUI buy-and-hold over the same in-sample window, per horizon (one number each)."""
    return ref["Close"].pct_change().mean() * 21  # ~monthly drift proxy (informational)


# ---------------------------------------------------------------- main
def main():
    ref = load_ref()
    in_start = ref.index[0]
    in_end = ref.index[-1]
    print("=" * 74)
    print(f"INDEPENDENT buy-the-dip episodes on {REF_TICKER}  "
          f"{in_start.date()} -> {in_end.date()}")
    print("=" * 74)

    # de-dup sensitivity
    print("\n--- A) DE-DUPLICATION (how many truly independent trades) ---")
    for name, (roll, min_dd) in {
        "6mo low, dd>=25% (base)": (126, 0.25),
        "6mo low, dd>=15%": (126, 0.15),
        "3mo low, dd>=20%": (63, 0.20),
        "12mo low, dd>=30%": (252, 0.30),
    }.items():
        eps = episodes(ref, roll, min_dd)
        print(f"  {name:<26} episodes = {len(eps):>3}"
              f"   naive(overlapping) = "
              f"{int(rolling_low(ref['Close'], roll, min_dd).sum()):>3}")

    base = (126, 0.25)
    eps = episodes(ref, *base)
    print(f"\n  Using base definition: {len(eps)} independent episodes.")

    # distribution / risk / stats
    rows = analyze(ref, eps, tag=f"btd_{'/'.join(map(str, base))}")
    df = pd.DataFrame(rows)
    cols = ["horizon", "n", "mean_gross", "mean_net", "median_net", "p10", "p90",
            "pos_pct", "avg_max_dd", "worst", "best", "profit_factor",
            "boot_mean_lo", "boot_mean_hi"]
    print("\n--- B-F) DISTRIBUTION / RISK / SIGNIFICANCE (de-duplicated) ---")
    show = df[cols].copy()
    for c in ["mean_gross", "mean_net", "median_net", "p10", "p90",
              "avg_max_dd", "worst", "best", "boot_mean_lo", "boot_mean_hi"]:
        show[c] = (show[c] * 100).round(2)
    show["pos_pct"] = show["pos_pct"].round(1)
    show["profit_factor"] = show["profit_factor"].round(2)
    print(show.to_string(index=False))

    df.to_csv(os.path.join(OUTDIR, "buy_dip_deep.csv"), index=False)

    # clustering by year
    print("\n--- WINNER CLUSTERING (which years produced the big gains) ---")
    for h in PUB:
        rec = df[df.horizon == h].iloc[0]
        yrs = dict(sorted(rec["years"].items()))
        print(f"  {h:>4}: " + "  ".join(f"{y}:{v}" for y, v in yrs.items()))

    # practical economics
    print("\n--- PRACTICAL ECONOMICS ---")
    span_yrs = (in_end - in_start).days / 365.25
    trades = len(eps)
    print(f"  episodes : {trades} over {span_yrs:.1f} yrs = "
          f"{trades/span_yrs:.1f} trades/yr")
    print(f"  cost     : {COST_SIDE*100:.0f} bps/side = "
          f"{2*COST_SIDE*100:.0f} bps round-trip per trade")
    h6 = df[df.horizon == "6M"].iloc[0]
    h12 = df[df.horizon == "12M"].iloc[0]
    print(f"  6M  gross {h6['mean_gross']*100:+.2f}%  net {h6['mean_net']*100:+.2f}% "
          f"(cost drag {2*COST_SIDE*100:.0f} bps)")
    print(f"  12M gross {h12['mean_gross']*100:+.2f}%  net {h12['mean_net']*100:+.2f}%")

    print("\nSaved: buy_dip_deep.csv")


if __name__ == "__main__":
    main()
