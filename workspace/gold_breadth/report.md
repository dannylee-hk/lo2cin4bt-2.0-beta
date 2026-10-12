# Gold Miners Breadth Thrust — Backtest Report

## Data
- Reference/tradable: ^HUI (Yahoo Finance)  1996-06-04 -> 2026-08-17
- Breadth basket (fixed, survivorship proxy): NEM, AEM, GFI, CDE, RGLD, F, PAAS, GOLD, ABX
- Pre-1996 (1970-1995) study window EXCLUDED.

## Signals detected
n = 21. Parameters: breadth < 10% then >= 50% in <= 15 sessions, first after a rolling-126-session low.

```
signal_date  breadth_at_trigger
 1997-08-18            0.571429
 1998-01-23            0.571429
 1998-10-01            0.571429
 1999-08-19            0.714286
 2000-02-24            0.571429
 2000-12-12            0.571429
 2005-02-28            0.571429
 2005-06-17            0.571429
 2008-12-12            0.571429
 2012-06-11            0.571429
 2013-08-09            0.714286
 2014-04-09            0.571429
 2015-05-01            0.625000
 2016-06-03            0.625000
 2018-01-08            0.750000
 2019-03-21            0.625000
 2020-08-28            0.875000
 2022-02-09            0.555556
 2022-10-26            0.555556
 2023-11-29            0.555556
 2026-08-14            0.777778
```

## Summary table (net)
```
        signal horizon    n  mean_ret  median_ret   pos_pct  avg_max_dd     mean   median       p10      p90      p95  max_dd_mean
breadth_thrust      1M   20 -0.027131   -0.054752 20.000000   -0.077744      NaN      NaN       NaN      NaN      NaN          NaN
breadth_thrust      3M   20 -0.023298   -0.002824 50.000000   -0.148755      NaN      NaN       NaN      NaN      NaN          NaN
breadth_thrust      5M   20 -0.030536   -0.070537 35.000000   -0.182728      NaN      NaN       NaN      NaN      NaN          NaN
breadth_thrust      6M   20 -0.028160   -0.085265 40.000000   -0.203397      NaN      NaN       NaN      NaN      NaN          NaN
breadth_thrust     12M   20 -0.000770   -0.049684 45.000000   -0.279113      NaN      NaN       NaN      NaN      NaN          NaN
      low_only      1M  305  0.007370   -0.001214 49.508197   -0.085419      NaN      NaN       NaN      NaN      NaN          NaN
      low_only      3M  305  0.032885    0.024506 53.114754   -0.138439      NaN      NaN       NaN      NaN      NaN          NaN
      low_only      5M  305  0.057697    0.015793 52.131148   -0.158281      NaN      NaN       NaN      NaN      NaN          NaN
      low_only      6M  305  0.076404    0.018516 55.409836   -0.165769      NaN      NaN       NaN      NaN      NaN          NaN
      low_only     12M  305  0.151401    0.011654 51.147541   -0.246281      NaN      NaN       NaN      NaN      NaN          NaN
  random_entry      1M 5000       NaN         NaN 52.140000         NaN 0.011467 0.005317 -0.119926 0.151580 0.197744    -0.067027
  random_entry      3M 5000       NaN         NaN 51.660000         NaN 0.027844 0.007302 -0.185699 0.277152 0.356091    -0.116826
  random_entry      5M 5000       NaN         NaN 52.600000         NaN 0.046814 0.013758 -0.245205 0.385575 0.526311    -0.148369
  random_entry      6M 5000       NaN         NaN 51.440000         NaN 0.060017 0.010226 -0.257795 0.449323 0.637155    -0.161740
  random_entry     12M 5000       NaN         NaN 53.540000         NaN 0.131732 0.037819 -0.341199 0.712118 0.951072    -0.220982
```

## Bootstrap CIs
```
                             0         1         2         3         4
signal_1M_mean       -0.027263       NaN       NaN       NaN       NaN
signal_1M_mean_lo    -0.055946       NaN       NaN       NaN       NaN
signal_1M_mean_hi     0.004717       NaN       NaN       NaN       NaN
signal_1M_median     -0.050461       NaN       NaN       NaN       NaN
signal_1M_median_lo  -0.068095       NaN       NaN       NaN       NaN
signal_1M_median_hi  -0.031976       NaN       NaN       NaN       NaN
signal_3M_mean             NaN -0.023380       NaN       NaN       NaN
signal_3M_mean_lo          NaN -0.090924       NaN       NaN       NaN
signal_3M_mean_hi          NaN  0.041495       NaN       NaN       NaN
signal_3M_median           NaN -0.006772       NaN       NaN       NaN
signal_3M_median_lo        NaN -0.089111       NaN       NaN       NaN
signal_3M_median_hi        NaN  0.080929       NaN       NaN       NaN
signal_5M_mean             NaN       NaN -0.031125       NaN       NaN
signal_5M_mean_lo          NaN       NaN -0.119808       NaN       NaN
signal_5M_mean_hi          NaN       NaN  0.061094       NaN       NaN
signal_5M_median           NaN       NaN -0.065031       NaN       NaN
signal_5M_median_lo        NaN       NaN -0.165239       NaN       NaN
signal_5M_median_hi        NaN       NaN  0.075125       NaN       NaN
signal_6M_mean             NaN       NaN       NaN -0.028268       NaN
signal_6M_mean_lo          NaN       NaN       NaN -0.120967       NaN
signal_6M_mean_hi          NaN       NaN       NaN  0.071243       NaN
signal_6M_median           NaN       NaN       NaN -0.081488       NaN
signal_6M_median_lo        NaN       NaN       NaN -0.176789       NaN
signal_6M_median_hi        NaN       NaN       NaN  0.061610       NaN
signal_12M_mean            NaN       NaN       NaN       NaN -0.000287
signal_12M_mean_lo         NaN       NaN       NaN       NaN -0.116041
signal_12M_mean_hi         NaN       NaN       NaN       NaN  0.120213
signal_12M_median          NaN       NaN       NaN       NaN -0.050186
signal_12M_median_lo       NaN       NaN       NaN       NaN -0.219373
signal_12M_median_hi       NaN       NaN       NaN       NaN  0.092545
```

## Sensitivity
Grid cells with pos>=80%:
```
Empty DataFrame
Columns: [low_thresh, high_thresh, window, horizon, n, mean_net, pos_pct]
Index: []
```

