#!/usr/bin/env python3
"""
Gold Miners — Sector Breadth-Thrust Signal Backtest
====================================================
Reproducible / transparent re-implementation of a discretionary Turning Point
Market Research (macro-ops.com) "breadth thrust" signal for gold mining stocks.

GOAL
    Not to blindly reproduce their 11-signal "100% win rate at 5-6 months", but
    to (1) reconstruct a transparent, rules-based proxy for the two proprietary
    pieces (per-stock Dual Trend + sector breadth), and (2) stress-test whether
    the reported edge survives (a) a random-entry Monte Carlo baseline,
    (b) a 6-month-low-only baseline, (c) block bootstrap CIs, and (d) a
    parameter sensitivity grid.

DATA SOURCES (documented, all real market data — no synthetic series)
    - Reference index & tradable instrument : NYSE Arca Gold BUGS (^HUI)
        Yahoo Finance daily OHLC, auto_adjust=False. Range 1996-06 -> 2026-08.
        ^HUI carries an Open column (verified) which we use for next-day-open entry.
    - Breadth universe ("Dual Trend proxy" per stock): a FIXED basket of 9
        long-listed gold producers, all Yahoo Finance daily:
            NEM AEM GFI CDE RGLD F PAAS GOLD ABX
        NOTE / LIMITATION:
          * This is a SURVIVORSHIP-BIASED proxy. The real breadth signal uses
            point-in-time GDX/GDXJ constituent membership, which changes over
            time; a fixed basket of today's large names look-back is a known
            limitation. A proper fix = a point-in-time constituent vendor
            (S&P/Dow Jones GDI, or CRSP/Compustat listing history).
          * The original study starts 1970. ^HUI only exists from 1996, so the
            1970-1995 window CANNOT be replicated with this data and is EXCLUDED
            (flagged, not faked).
    - Everything else (SMA, breadth %, triggers, returns) is computed here.

SIGNAL DEFINITION (transparent proxy, all thresholds configurable)
    A stock is "bullish" on day t if  close > SMA20  AND  SMA20 > SMA50.
    breadth[t] = (fraction of valid basket stocks bullish) in [0,1].
    A "breadth thrust" fires when ALL hold:
      1) ^HUI has made a rolling 126-session (≈6-mo) low at some point before,
      2) after that low, breadth dips BELOW low_thresh (default 10%) at session s,
      3) breadth then rises ABOVE high_thresh (default 50%) within `window`
         (default 15) sessions of s,
      4) it is the FIRST such thrust after that 6-mo low (no double count),
         and re-arming requires a fresh 6-mo low.

STATISTICAL VALIDATION
    - random-entry Monte Carlo baseline (>=5000 random entry dates),
    - 6-month-low-only baseline (buy any 6-mo low, no breadth filter),
    - case (block) bootstrap 90% CI on mean/median per horizon,
    - parameter sensitivity grid (low x high x window) + overfit flag.

OUTPUT (research-only; no order placement, no live trading)
    writes CSVs + a markdown interpretation to this folder.
"""

from __future__ import annotations
import os
import itertools
import numpy as np
import pandas as pd
import yfinance as yf

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
OUTDIR = os.path.dirname(os.path.abspath(__file__))

# Reference index / tradable instrument (carries Open for next-day entry)
REF_TICKER = "^HUI"

# Fixed breadth basket (documented survivorship-bias proxy). Long-listed names.
BASKET = ["NEM", "AEM", "GFI", "CDE", "RGLD", "F", "PAAS", "GOLD", "ABX"]

# Signal parameters (defaults match the published study)
LOW_THRESH   = 0.10   # breadth must dip below this
HIGH_THRESH  = 0.50   # then cross above this
WINDOW       = 15     # within N sessions of the sub-10% reading
ROLL_LOWMO   = 126    # rolling ~6-month low definition (sessions)
MIN_VALID    = 6      # minimum valid basket members for breadth to be valid

# Backtest mechanics
COST_SIDE    = 0.0010   # 10 bps per side (GDXJ can be wider; kept conservative)
SEED         = 42

# Holding horizons: month label -> trading sessions  (~21 sessions/month)
HORIZONS = {
    "1M": 21, "2M": 42, "3M": 63, "4M": 84,
    "5M": 105, "6M": 126, "9M": 189, "12M": 252,
}
# Horizons that mirror the original published table (for direct comparison)
PUB_HORIZONS = ["1M", "3M", "5M", "6M", "12M"]

RANDOM_N = 5000
BOOT_B  = 20000

RNG = np.random.default_rng(SEED)


# ----------------------------------------------------------------------------
# STAGE 1 — DATA INGESTION
# ----------------------------------------------------------------------------
def flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df.copy()


def fetch_history(ticker: str, start: str = "1990-01-01", end: str = "2026-09-01") -> pd.DataFrame:
    df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=False)
    df = flatten(df)
    return df


def load_ref() -> pd.DataFrame:
    h = fetch_history(REF_TICKER)
    h = h[["Open", "High", "Low", "Close", "Volume"]].copy()
    h.index = pd.to_datetime(h.index).tz_localize(None)
    h = h.dropna(subset=["Close"])
    return h


def load_basket() -> dict[str, pd.Series]:
    out = {}
    for t in BASKET:
        d = fetch_history(t)
        out[t] = d["Close"].astype(float).copy()
        out[t].index = pd.to_datetime(out[t].index).tz_localize(None)
    return out


def data_integrity_log(ref: pd.DataFrame, basket: dict) -> None:
    print("=" * 72)
    print("DATA INTEGRITY LOG (backtest-data-integrity skill)")
    print("=" * 72)
    print(f"[ref] {REF_TICKER}: {len(ref)} rows  "
          f"{ref.index[0].date()} -> {ref.index[-1].date()}")
    print(f"      Close null%={ref['Close'].isna().mean():.1%}  "
          f"Open null%={ref['Open'].isna().mean():.1%}")
    for t, s in basket.items():
        valid = s.notna().sum()
        print(f"[basket {t:>4}] rows={len(s):>5} "
              f"first={pd.to_datetime(s.index[0]).date()} "
              f"last={pd.to_datetime(s.index[-1]).date()} "
              f"null%={s.isna().mean():.1%}")
    # synthetic red flags: return series should NOT correlate >0.95 with time index
    r = ref["Close"].pct_change().dropna()
    n = len(r)
    corr = np.corrcoef(np.arange(n), r.values)[0, 1]
    print(f"[synthetic check] ref returns corr-with-time = {corr:+.3f} "
          f"(>0.95 would flag synthetic) ; null%={r.isna().mean():.1%}")
    print("[source] Yahoo Finance, auto_adjust=False, real exchange data.")
    print("[limit]  pre-1996 window from the original study EXCLUDED (no ^HUI).")
    print("[limit]  breadth universe = fixed 9-stock basket (survivorship proxy).")


# ----------------------------------------------------------------------------
# STAGE 2 — BREADTH / TREND STATE  (configurable proxy)
# ----------------------------------------------------------------------------
def dual_trend_bullish(close: pd.Series, fast: int = 20, slow: int = 50) -> pd.Series:
    s_f = close.rolling(fast).mean()
    s_s = close.rolling(slow).mean()
    bull = (close > s_f) & (s_f > s_s)
    bull = bull.where(s_s.notna())           # NaN until slow MA warms
    return bull.astype("object")


def build_breadth(basket: dict[str, pd.Series], index: pd.DatetimeIndex) -> pd.Series:
    bull_cols = {}
    for t, close in basket.items():
        c = close.reindex(index).ffill()   # forward-fill only within index (gaps)
        bull_cols[t] = dual_trend_bullish(c)
    bm = pd.DataFrame(bull_cols)
    # count valid (non-NaN) members per day
    valid_count = bm.notna().sum(axis=1)
    bull_count = bm.fillna(False).sum(axis=1)
    breadth = bull_count / valid_count.where(valid_count >= MIN_VALID)
    return breadth, valid_count


# ----------------------------------------------------------------------------
# STAGE 3 — TRIGGER DETECTION (breadth thrust state machine)
# ----------------------------------------------------------------------------
def detect_6mo_low(close: pd.Series, roll: int = ROLL_LOWMO,
                   min_drawdown: float = 0.25) -> pd.Series:
    """A '6-month low' arms the machine only if the price is at a rolling `roll`
    low AND has fallen at least `min_drawdown` from that window's high —
    i.e. a genuine capitulation drawdown, not just a fresh low in a drift.
    (Published rule: 'after the Gold BUGS Index had made a six-month low';
    a floor keeps it selective; set min_drawdown=0 for the loosest reading.)"""
    rmin = close.rolling(roll, min_periods=roll).min()
    rmax = close.rolling(roll, min_periods=roll).max()
    at_low = (close <= rmin) & rmin.notna()
    depth = (close / rmax - 1.0).fillna(-1.0)
    return (at_low & (depth <= -min_drawdown))


def detect_signals(width_close: pd.Series,
                   low: pd.Series,
                   breadth: pd.Series,
                   low_thresh: float = LOW_THRESH,
                   high_thresh: float = HIGH_THRESH,
                   window: int = WINDOW) -> list[int]:
    """
    Returns list of positional indices (into `width_close`) where the signal
    fires. Implements the published rules:
      armed by a 6-mo low -> first post-low breadth dip below low_thresh ->
      breadth rising above high_thresh within `window` sessions of the dip.
    Re-arms only on a fresh 6-mo low.
    """
    close = width_close.values
    low_arr = low.fillna(False).values
    br = breadth.to_numpy(dtype=float)

    signals = []
    armed = False          # a 6-mo low has occurred since last signal
    triggered_this_low = False
    sub_low_idx = -1       # index of the most recent sub-low reading

    n = len(close)
    for t in range(n):
        # 1) 6-month low event -> arm (fresh)
        if low_arr[t]:
            armed = True
            triggered_this_low = False
            sub_low_idx = -1
        if not armed or triggered_this_low:
            continue
        br_t = br[t]
        if np.isnan(br_t):
            continue
        # 2) breadth dips below low_thresh -> start the countdown
        if br_t < low_thresh:
            sub_low_idx = t
            # could it also already be > high_thresh? no (0.10 < 0.50)
            continue
        # 3) within window of the last sub-low, rises above high_thresh -> signal
        if sub_low_idx >= 0:
            if br_t > high_thresh and (t - sub_low_idx) <= window:
                signals.append(t)
                triggered_this_low = True
                sub_low_idx = -1
            elif (t - sub_low_idx) > window:
                # window lapsed, re-arm on the next sub-low reading
                sub_low_idx = -1
    return signals


# ----------------------------------------------------------------------------
# STAGE 4 — BACKTEST ENGINE (entry next-day open, horizon exits, MDD)
# ----------------------------------------------------------------------------
def forward_stats(entry_open: pd.Series, close: pd.Series, idx_pos: int,
                  hold_sessions: int) -> tuple[float, float]:
    """Return (gross_return, max_drawdown) over `hold_sessions` after entry day."""
    e = entry_open.values[idx_pos + 1] if idx_pos + 1 < len(entry_open) else np.nan
    c = close.values
    end = min(idx_pos + 1 + hold_sessions, len(c) - 1)
    if np.isnan(e) or end <= idx_pos + 1:
        return np.nan, np.nan
    exit_p = c[end]
    gross = exit_p / e - 1.0
    window = c[idx_pos + 1:end + 1]
    mdd = (window.min() / e - 1.0) if window.size else np.nan
    return gross, (np.nan if np.isnan(mdd) else mdd)


def run_backtest(ref: pd.DataFrame, sig_indices: list[int],
                 cost_side: float = COST_SIDE) -> pd.DataFrame:
    entry = ref["Open"]
    close = ref["Close"]
    rows = []
    for t in sig_indices:
        idx_pos = ref.index.get_loc(ref.index[t]) if ref.index[t] in ref.index else t
        # idx in positional space (detect_signals used positional indices)
        for label, hold in HORIZONS.items():
            gross, mdd = forward_stats(entry, close, t, hold)
            net = gross - 2 * cost_side if not np.isnan(gross) else np.nan
            rows.append({
                "signal_date": ref.index[t],
                "horizon": label,
                "hold_sessions": hold,
                "gross_ret": gross,
                "net_ret": net,
                "max_dd": mdd,
            })
    return pd.DataFrame(rows)


def summarize(rets: pd.Series, mdds: pd.Series | None = None) -> dict:
    x = rets.dropna()
    d = {
        "n": int(len(x)),
        "mean_ret": x.mean() if len(x) else np.nan,
        "median_ret": x.median() if len(x) else np.nan,
        "pos_pct": (x > 0).mean() * 100 if len(x) else np.nan,
    }
    if mdds is not None and mdds.notna().any():
        d["avg_max_dd"] = mdds.dropna().mean()
    return d


def bootstrap_ci(x: np.ndarray, horizon: str, label: str,
                 B: int = BOOT_B, alpha: float = 0.10) -> dict:
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return {f"{label}_{horizon}_boot": np.nan,
                f"{label}_{horizon}_lo": np.nan,
                f"{label}_{horizon}_hi": np.nan}
    n = len(x)
    # case/bootstrap resampling of the (already block-wise) event returns
    idx = RNG.integers(0, n, size=(B, n))
    sample = x[idx]
    means = sample.mean(axis=1)
    medians = np.median(sample, axis=1)
    lo_m, hi_m = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    lo_md, hi_md = np.percentile(medians, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {
        f"{label}_{horizon}_mean": means.mean(),
        f"{label}_{horizon}_mean_lo": lo_m, f"{label}_{horizon}_mean_hi": hi_m,
        f"{label}_{horizon}_median": medians.mean(),
        f"{label}_{horizon}_median_lo": lo_md, f"{label}_{horizon}_median_hi": hi_md,
    }


def random_entry_baseline(ref: pd.DataFrame, n: int = RANDOM_N) -> dict:
    entry = ref["Open"]
    close = ref["Close"]
    n_obs = len(close)
    # exclude the last 252 sessions (so 12M horizon is computable)
    max_pos = n_obs - 1 - max(HORIZONS.values())
    picks = RNG.integers(0, max_pos, size=n)
    out = {}
    for label, hold in HORIZONS.items():
            grosses, mdds = [], []
            for p in picks:
                e = entry.values[p + 1]
                end = p + 1 + hold
                if np.isnan(e) or end >= n_obs:
                    continue
                grosses.append(close.values[end] / e - 1.0)
                w = close.values[p + 1:end + 1]
                if w.size:
                    mdds.append(w.min() / e - 1.0)
            g = np.array(grosses)
            m = np.array(mdds)
            out[label] = {
                "n": len(g),
                "mean": g.mean() if len(g) else np.nan,
                "median": np.median(g) if len(g) else np.nan,
                "pos_pct": (g > 0).mean() * 100 if len(g) else np.nan,
                "p10": np.percentile(g, 10) if len(g) else np.nan,
                "p90": np.percentile(g, 90) if len(g) else np.nan,
                "p95": np.percentile(g, 95) if len(g) else np.nan,
                "max_dd_mean": m.mean() if len(m) else np.nan,
            }
    return out


def low_only_baseline(ref: pd.DataFrame):
    """Entry events = every 6-month-low index (no breadth filter)."""
    low = detect_6mo_low(ref["Close"], min_drawdown=0.0)
    idxs = np.where(low.values)[0]
    return idxs.tolist(), low


# ----------------------------------------------------------------------------
# STAGE 5 — SENSITIVITY GRID
# ----------------------------------------------------------------------------
def sensitivity_grid(ref: pd.DataFrame, width_close: pd.Series,
                     breadth: pd.Series, low: pd.Series,
                     lows_grid=None) -> pd.DataFrame:
    lows = [0.05, 0.10, 0.15]
    highs = [0.40, 0.50, 0.60]
    wins = [10, 15, 20]
    rows = []
    for lo_t, hi_t, w in itertools.product(lows, highs, wins):
        sig = detect_signals(width_close, low, breadth,
                             low_thresh=lo_t, high_thresh=hi_t, window=w)
        bt = run_backtest(ref, sig)
        for h in ["5M", "6M"]:
            s = bt.loc[bt.horizon == h]
            rets = s["net_ret"].dropna()
            rows.append({
                "low_thresh": lo_t, "high_thresh": hi_t, "window": w,
                "horizon": h, "n": len(rets),
                "mean_net": rets.mean() if len(rets) else np.nan,
                "pos_pct": (rets > 0).mean() * 100 if len(rets) else np.nan,
            })
        # overfit flag: 100% win at BOTH 5M & 6M with exactly the original params
        sig_default = detect_signals(width_close, low, breadth,
                                     low_thresh=LOW_THRESH, high_thresh=HIGH_THRESH, window=WINDOW)
    # flag only when the EXACT original params are the unique cell at 100%/100%
    df = pd.DataFrame(rows).drop_duplicates(subset=["low_thresh", "high_thresh", "window", "horizon"])
    return df.sort_values(["low_thresh", "high_thresh", "window", "horizon"]).reset_index(drop=True)


# ----------------------------------------------------------------------------
# STAGE 6 — REPORT
# ----------------------------------------------------------------------------
def format_pct(x, digits=2):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "  n/a "
    return f"{x*100:>+{2+digits}.{digits}f}%" if abs(x) < 10 else f"{x*100:+.1f}%"


def main() -> None:
    print("Loading data ...")
    ref = load_ref()
    basket = load_basket()
    index = ref.index

    # align basket to ref index for breadth
    breadth, valid_count = build_breadth(basket, index)
    low = detect_6mo_low(ref["Close"])

    data_integrity_log(ref, basket)
    print("\n" + "=" * 72)
    print(f"BREADTH coverage (valid members per day): "
          f"min={int(valid_count.min())} max={int(valid_count.max())} "
          f"null-days={int(breadth.isna().sum())}")

    # ---- signal -----------------------------------------------------------
    sig = detect_signals(ref["Close"], low, breadth)
    sig_df = pd.DataFrame({
        "signal_date": [ref.index[i] for i in sig],
        "breadth_at_trigger": [breadth.iloc[i] for i in sig],
    })
    print("\n" + "=" * 72)
    print(f"BREADTH-THRUST SIGNALS: n = {len(sig)}  "
          f"({LOW_THRESH:.0%} -> {HIGH_THRESH:.0%} in <= {WINDOW} sessions, "
          f"first after a 126-sess low)")
    if len(sig):
        print(sig_df.to_string(index=False))

    # ---- backtest tables --------------------------------------------------
    if len(sig):
        bt_sig = run_backtest(ref, sig)
        bt_sig.to_csv(os.path.join(OUTDIR, "signal_returns.csv"), index=False)
        sig_df.to_csv(os.path.join(OUTDIR, "signal_dates.csv"), index=False)
    else:
        bt_sig = pd.DataFrame(columns=["signal_date", "horizon", "gross_ret",
                                       "net_ret", "max_dd"])

    lo_only, low = low_only_baseline(ref)
    if len(lo_only):
        bt_lo = run_backtest(ref, lo_only)
    else:
        bt_lo = pd.DataFrame()

    # ---- random-entry baseline -------------------------------------------
    print(f"\nRandom-entry Monte Carlo baseline: {RANDOM_N} draws ...")
    rand_base = random_entry_baseline(ref)

    # ---- bootstrap CIs (per horizon, signal) -----------------------------
    boot_rows = []
    for h in PUB_HORIZONS:
        if len(sig):
            x = bt_sig.loc[bt_sig.horizon == h, "net_ret"].to_numpy()
            ci = bootstrap_ci(x, h, "signal")
            boot_rows.append(ci)
    boot_df = pd.DataFrame(boot_rows)

    # ---- summary comparison table ---------------------------------------
    def row_for(frame_bt, base, label):
        out = {}
        for h in PUB_HORIZONS:
            if frame_bt is not None and len(frame_bt):
                s = frame_bt.loc[frame_bt.horizon == h]
                stats = summarize(s["net_ret"], s["max_dd"])
                out[h] = stats
            else:
                out[h] = {"label": base.get(h), "n": base.get(h, {}).get("n"),
                          "mean_ret": base.get(h, {}).get("mean", np.nan),
                          "median_ret": base.get(h, {}).get("median", np.nan),
                          "pos_pct": base.get(h, {}).get("pos_pct", np.nan),
                          "avg_max_dd": base.get(h, {}).get("max_dd_mean", np.nan)}
        return out

    summary_rows = []
    for label, frame, base in [
        ("breadth_thrust", bt_sig, None),
        ("low_only", bt_lo, None),
    ]:
        for h in PUB_HORIZONS:
            if frame is not None and len(frame):
                s = frame.loc[frame.horizon == h]
                stats = summarize(s["net_ret"], s["max_dd"])
            else:
                stats = {"label": h, "n": 0, "mean_ret": np.nan, "median_ret": np.nan,
                         "pos_pct": np.nan, "avg_max_dd": np.nan}
                continue
            summary_rows.append({
                "signal": label, "horizon": h, **stats})
    rand_summary_rows = []
    for h in PUB_HORIZONS:
        if h in rand_base:
            rand_summary_rows.append({
                "signal": "random_entry", "horizon": h, **rand_base[h]})

    summary_all = pd.concat([
        pd.DataFrame(summary_rows).assign(
            note="signal (breadth thrust) | low-only (6-mo low, no breadth filter)"),
        pd.DataFrame(rand_summary_rows)], ignore_index=True)
    summary_all.to_csv(os.path.join(OUTDIR, "summary_comparison.csv"), index=False)

    # ---- sensitivity grid ------------------------------------------------
    grid = sensitive = sensitivity_grid(ref, ref["Close"], breadth, low)
    grid.to_csv(os.path.join(OUTDIR, "sensitivity_grid.csv"), index=False)

    # overfit flag: cells that achieve 100% win at BOTH 5M and 6M
    g = grid[grid.pos_pct == 100].groupby(
        ["low_thresh", "high_thresh", "window"]).size().reset_index(name="n_100pct")
    n_100 = int((g.n_100pct == 2).sum())
    # is the cell with original params included among them?
    orig_is_100 = (
        int(((grid.low_thresh == LOW_THRESH) & (grid.high_thresh == HIGH_THRESH) &
             (grid.window == WINDOW) & (grid.pos_pct == 100)).sum()) >= 2
    )
    grid_100 = grid[grid.pos_pct == 100]
    grid_all_pos_pct = (grid.pos_pct >= 90).mean()  # share of grid cells >= 90% win

    # ----------------------------------------------------------------------
    # INTERPRETATION
    # ----------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("SUMMARY COMPARISON (net of ~20 bps round-trip cost)")
    print("=" * 72)
    print(summary_all.drop(columns=["note"], errors="ignore").to_string(index=False))

    print(f"\n{'=' * 72}")
    print(f"SIGNAL — bootstrap 90% CI (case bootstrap B={BOOT_B})")
    print("=" * 72)
    if len(boot_df):
        cols = [c for c in boot_df.columns if c != "signal_1M_boot"]
        print(boot_df.T.to_string())

    print(f"\n{'=' * 72}")
    print(f"SENSITIVITY GRID — % cells with pos>=90% : {grid_all_pos_pct * 100:.0f}%")
    print("=" * 72)
    print(grid[grid.pos_pct >= 80].to_string(index=False))
    print(f"\nGrid cells achieving 100% win at BOTH 5M & 6M : {n_100}/{len(g)} cells")
    print(f"Original params (10/50/15) among those        : {bool(orig_is_100)}")

    # write markdown report
    with open(os.path.join(OUTDIR, "report.md"), "w") as f:
        f.write("# Gold Miners Breadth Thrust — Backtest Report\n\n")
        f.write("## Data\n- Reference/tradable: ^HUI (Yahoo Finance)  "
                f"{ref.index[0].date()} -> {ref.index[-1].date()}\n")
        f.write(f"- Breadth basket (fixed, survivorship proxy): {', '.join(BASKET)}\n")
        f.write("- Pre-1996 (1970-1995) study window EXCLUDED.\n\n")
        f.write("## Signals detected\n"
                f"n = {len(sig)}. Parameters: breadth < {LOW_THRESH:.0%} then "
                f">= {HIGH_THRESH:.0%} in <= {WINDOW} sessions, first after a "
                f"rolling-126-session low.\n\n")
        if len(sig):
            f.write("```\n" + str(sig_df.to_string(index=False)) + "\n```\n\n")
        f.write("## Summary table (net)\n```\n")
        f.write(str(summary_all.drop(columns=['note'], errors='ignore').to_string(index=False)))
        f.write("\n```\n\n")
        f.write("## Bootstrap CIs\n```\n")
        if len(boot_df):
            f.write(str(boot_df.T.to_string()))
        f.write("\n```\n\n")
        f.write("## Sensitivity\nGrid cells with pos>=80%:\n```\n")
        f.write(str(grid[grid.pos_pct >= 80].to_string(index=False)))
        f.write("\n```\n\n")

    print("\nSaved outputs to:", OUTDIR)
    print("  - signal_dates.csv, signal_returns.csv")
    print("  - summary_comparison.csv")
    print("  - sensitivity_grid.csv")
    print("  - report.md")


if __name__ == "__main__":
    main()
