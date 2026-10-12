# TQQQ Crisis Rebound — Research Notes

Local research only. Not live-trading authorization.

**Pipeline (canonical):** [`pipeline/PIPELINE.md`](pipeline/PIPELINE.md) · [`pipeline/PIPELINE.html`](pipeline/PIPELINE.html)  
**Plan (legacy probe):** [`STRATEGY_PLAN.md`](STRATEGY_PLAN.md) · **Diagnostic only:** [`all_gates_results.html`](all_gates_results.html)

## HY OAS proxy（only 3）

1. ICE full `BAMLH0A0HYM2` (best; public FRED ~3y)
2. `BAA10Y` (acceptable long history; not HY)
3. `HYG/IEF` or `HYG/LQD` (ETF PROXY)

## All-gates run (2026-08-03)

Command: `run_all_gates.py`

### Gate1+2 (QQQ crashes) — pass_both rate

| ID | Indicator | Both | G1 | Med lead | G2 | Note |
| --- | --- | --- | --- | --- | --- | --- |
| A2 | Swap 3M/10Y | **0.6** | 0.6 | 41d | 0.8 | pre-2016 only |
| A3 | Funding PROXY | **0.6** | 0.6 | 28d | 0.8 | not SOFR-OIS |
| D2 | VX back PROXY | **0.6** | 0.8 | 23d | 0.8 | VIX−VIX3M |
| B2 | BAA10Y | 0.5 | 0.5 | 19d | 0.9 | long HY-sub |
| D | VIX | 0.5 | 0.5 | 18d | 1.0 | |
| E | MOVE stack | 0.5 | 0.5 | 27d | 1.0 | |
| B3a/b | HYG stress | 0.4 | 0.6–0.8 | 30–59d | 0.4 | ETF PROXY |
| C | Baa−Aaa | 0.2 | 0.2 | 38d | 0.8 | Macro gate weak |
| A | Swap10 | 0.0 | 1.0 | 85d | **0.0** | leads but no trough align |
| B | HY OAS | — | — | — | — | **DATA_BLOCKED** on labeled crashes (public 3y) |

### Gate3 harness best cell (TQQQ; costs 10+5bps/side)

Caveat: low thresholds ≈ high time-in-market; best CAGR ≠ OOS edge. Most MaxDD still ~−60% to −80%.

| ID | Best thr / hold | Trades | CAGR | MaxDD | vs TQQQ BH |
| --- | --- | --- | --- | --- | --- |
| B2 | 2.0 / 200 | 17 | 45.5% | −72.6% | BH 42.0% — **suspect always-in bias** |
| B3b | −2.0 / 290 | 12 | 43.4% | −75.3% | slight > BH |
| A2 | −100 / 290 | 5 | 43.5% | −43.9% | sample→2016 only ≈ BH |
| D2 | 0 / 290 | 12 | 36.6% | −74.8% | < BH |
| B3a | −1 / 120 | 26 | 38.5% | −74.5% | < BH |
| E | 0.5 / 290 | 13 | 32.3% | −81.3% | < BH |
| C | 100 / 290 | 9 | 31.9% | −74.0% | < BH |
| D | 40 / 290 | 5 | 26.2% | −61.4% | < BH |
| A3 | −15 / 290 | 8 | 23.7% | −58.2% | < BH |
| A | 20 / 60 | 6 | 23.6% | −28.3% | < BH (→2016) |
| B | 4.5 / 290 | 2 | 124% | −37.4% | **3y smoke only — not evidence** |

### Engine validation

`workspace_doctor` passed all new `strategy-run-tqqq-*-hold-smoke-proxy.json`.  
UnifiedBacktestRunner smoke OK for C / B2 / D2 (4 combos each).

## Rebuild

```powershell
.\.venv\Scripts\python.exe workspace/reports/agents/tqqq_crisis_rebound_proxy/run_all_gates.py
Start-Process workspace/reports/agents/tqqq_crisis_rebound_proxy/all_gates_results.html
```
