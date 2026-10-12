# BTC 賣方力竭常數（SEC）lo2cin4bt 驗證計畫

## Goal

以 BTC 日線價格與具明確版本/可觀測時間的 PSIP 序列，驗證 SEC = PSIP × 年化 30 日波動率在極低讀數後的 30/90/180/365 日前向回報、失效條件及樣本限制，並產出可重現的 Markdown 與 self-contained HTML 報告。

## Current context / assumptions

- Repo：`D:\trading\lo2cin4bt-v2`；Python 入口使用 `D:\trading\lo2cin4bt-v2\.venv\Scripts\python.exe`。
- 原始 prompt：`D:\danny_mind\01_Trading\backtest\lo2cin4bt-Prompt_BTC賣方力竭指標驗證.md`。prompt 定義 SEC、expanding percentile、thresholds、horizons、檢驗 A–E、輸出及事前判讀門檻。
- Repo source of truth：`README.md`、`AGENTS.md`、`skills/lo2cin4bt/SKILL.md`、`docs/ai/AI_MANUAL_SKILL.md`、`skills/lo2cin4bt-backtesting/SKILL.md`。
- `D:\hermes\skills\quantitative-trading\lo2cin4-backtest-report\SKILL.md` 是可讀到的 private workflow；其提到的 `lo2cin4bt-strategy-builder` 與 `skills/lo2cin4bt-backtesting` 路徑部分已漂移，執行者必須以本 repo 實際檔案和目前 schema 為準。
- 這是事件研究，不是下單策略。不得把 SEC signal 包裝成已支援的投資策略，也不得進行 live trading。
- 資料標籤必須分開：BTC 價格 = real（需記錄 provider/symbol/fetch time）；PSIP = real 或 proxy（若無 point-in-time/版本證據，標為 proxy/limited）；funding/net-flow = optional proxy。
- 先假設使用本機可取得的 PSIP CSV；若 prompt 指定源無法取得，不能默默以 synthetic data 代替，應停在 `DATA_INSUFFICIENT` 並報告缺口。
- 研究核心輸出放在 `workspace/reports/agents/btc_sec/`；不寫入 Obsidian vault，不提交 runtime outputs/logs/cache。

## Architecture / proposed approach

建立一個可重現的資料管線：raw input → schema/quality report → aligned feature table → vectorized SEC/event statistics → report builders。lo2cin4bt 的 `strategy_run` 只在能力檢查後用於必要的 price/signal execution cross-check；Welch t-test、bootstrap CI、12-combination multiple-testing correction、event-study 與 failure tests 由 workspace research module 明確實作，並在報告中標示不是 engine-native evidence。

## Step-by-step tasks

### 1. 建立 research skeleton 與 baseline contract

新增：

- `workspace/reports/agents/btc_sec/sec_pipeline.py`
- `workspace/reports/agents/btc_sec/test_sec_pipeline.py`
- `workspace/reports/agents/btc_sec/README.md`

先寫 failing tests，至少覆蓋：

```python
def test_sec_uses_annualized_30d_log_return_volatility():
    frame = make_fixture_frame()
    out = build_features(frame)
    expected = out["psip"] * out["vol30_annualized"]
    assert out["sec"].equals(expected)

def test_expanding_percentile_excludes_current_observation():
    frame = make_fixture_frame()
    out = build_features(frame)
    assert out.loc["2020-01-02", "sec_expanding_percentile"] == pytest.approx(
        out.loc[:"2020-01-01", "sec"].rank(pct=True).iloc[-1]
    )

def test_future_return_is_close_t_plus_h_over_close_t_minus_one():
    frame = make_fixture_frame()
    out = build_features(frame, horizons=(2,))
    assert out.loc["2020-01-01", "r_fwd_2"] == pytest.approx(
        frame.loc["2020-01-03", "close"] / frame.loc["2020-01-01", "close"] - 1
    )
```

驗證失敗：

```powershell
& .\.venv\Scripts\python.exe -m pytest workspace\reports\agents\btc_sec\test_sec_pipeline.py -q
```

預期：`3 failed`，因 implementation 尚未存在。之後用最少 pandas/numpy code 實作欄位：`log_return`、`vol30_annualized = log_return.rolling(30).std() * sqrt(365)`、`sec`、expanding percentile（只使用 `shift(1)` 的歷史資料）、`r_fwd_{30,90,180,365}`、prior-365-day drawdown。再跑同一命令，預期全部 pass；commit：`git add workspace/reports/agents/btc_sec && git commit -m "test btc sec feature definitions"`。

### 2. 固定資料格式、來源與 point-in-time 閘門

新增：

- `workspace/reports/agents/btc_sec/data_contract.json`
- `workspace/reports/agents/btc_sec/test_data_contract.py`

`data_contract.json` 必須明列：`price_provider`、`price_symbol`、`price_frequency`、`price_start`、`psip_source_url_or_path`、`observed_at`、`usable_from`、`point_in_time`、`revision_policy`、`fetch_time_utc`、`data_label`。測試必須拒絕缺少 `point_in_time` 或 `revision_policy` 的 PSIP contract，並拒絕重複日期、非遞增日期、PSIP 不在 `[0,1]`、價格非正數。

驗證：

```powershell
& .\.venv\Scripts\python.exe -m pytest workspace\reports\agents\btc_sec\test_data_contract.py -q
```

預期：fixture 先 fail，再完成 validator 後 pass。只在已有真實檔案時新增 `workspace/datasets/btc_sec/price.csv` 與 `psip.csv`；若資料不存在，建立 `DATA_MISSING.md`，不要造假資料。commit：`git add workspace/reports/agents/btc_sec && git commit -m "add btc sec data contract"`。

### 3. 下載/匯入並完成資料質量報告

新增：

- `workspace/reports/agents/btc_sec/fetch_data.py`
- `workspace/reports/agents/btc_sec/test_fetch_data.py`
- `workspace/reports/agents/btc_sec/data_quality_report.json`

`fetch_data.py` 必須支援本機 CSV 優先、明確 URL fallback；價格使用 BTC-USD 或 Binance BTCUSDT daily，但只選一個作 primary，另一個只能作 robustness。對 PSIP：若免費 CSV 需手動下載，要求執行者把檔案放入 `workspace/datasets/btc_sec/psip.csv`，程式只驗證不猜測。merge 時以日曆日 inner/left join 的選擇寫入報告；PSIP 週頻只能 forward-fill 並記錄 `psip_frequency=weekly`，不得填補價格缺口。

驗證命令：

```powershell
& .\.venv\Scripts\python.exe workspace\reports\agents\btc_sec\fetch_data.py --price-provider binance --price-symbol BTCUSDT --start 2010-07-19
```

預期：若資料完整，輸出 `merged_data.csv` 和 `data_quality_report.json`，並打印 `price_rows=... psip_rows=... merged_rows=...`；若 PSIP 缺失，退出非零並打印 `DATA_INSUFFICIENT: missing PSIP input`。測試：

```powershell
& .\.venv\Scripts\python.exe -m pytest workspace\reports\agents\btc_sec\test_fetch_data.py -q
```

預期所有資料缺口、日期排序、warmup、forward-fill 規則測試 pass。commit：`git add workspace/reports/agents/btc_sec && git commit -m "add btc sec data quality gate"`。

### 4. 實作事件、A–E 統計與事前判讀規則

新增：

- `workspace/reports/agents/btc_sec/analyse_sec.py`
- `workspace/reports/agents/btc_sec/test_analyse_sec.py`

Implementation 必須輸出：

- `events_table.csv`：連續 signal_extreme 區間、start/end、最低 SEC、各 horizon forward return、90 日新低、90 日內跌超過 15% joint event。
- `decile_stats.csv`：SEC expanding percentile 十分位及 `r_fwd_365` mean/median/count/CI。
- `stats_summary.json`：A Welch t-test、bootstrap 95% CI、threshold × horizon 12 組 raw/Bonferroni p-value、樣本數門檻、資料標籤。
- optional `leverage_condition_stats.csv`：funding 或 exchange net-flow proxy 的分組結果；沒有可靠序列時輸出 `not_generated`，不是 0。

Tests 先寫並確認 fail，再實作：

- `<8` 個 trigger 只允許 `descriptive_only=true`，不得輸出「勝率」判斷。
- expanding percentile 不得看未來資料。
- signal thresholds 正確覆蓋 `0.03/0.01/0.05` 及 `0.007/0.005`。
- horizon 未來資料不足時為 NaN 並從該 horizon 統計排除。
- event periods 合併相鄰 trigger days，避免把同一事件重複計數。
- Bonferroni 使用 `min(raw_p * 12, 1.0)`，且報告明確說明這是 prompt 指定的簡化 multiple-testing correction，不冒稱完整 Deflated Sharpe/White reality check。

驗證：

```powershell
& .\.venv\Scripts\python.exe -m pytest workspace\reports\agents\btc_sec\test_analyse_sec.py -q
& .\.venv\Scripts\python.exe workspace\reports\agents\btc_sec\analyse_sec.py --input workspace\reports\agents\btc_sec\merged_data.csv --out workspace\reports\agents\btc_sec
```

預期：測試全 pass；分析命令輸出四個檔案或明確 `DATA_INSUFFICIENT`，不會把缺資料當作零。commit：`git add workspace/reports/agents/btc_sec && git commit -m "add btc sec event study"`。

### 5. lo2cin4bt capability/engine cross-check（只在資料完整後）

新增：

- `workspace/runs/strategy-run-btc-sec-crosscheck.json`（只在 schema 能表達 signal 且 `workspace_doctor` 通過後）
- `workspace/reports/agents/btc_sec/run_engine_crosscheck.py`
- `workspace/reports/agents/btc_sec/test_engine_crosscheck.py`

先檢查 `backtester/contracts/strategy/strategy-run.schema.json`、`backtester/ops/registry.py`、`backtester/Percentile_Indicator_backtester.py`、`backtester/UnifiedBacktestRunner_backtester.py`，確認 external PSIP feature、expanding percentile、forward-return event study、Welch/bootstrap 是否 engine-supported。不能表達時只產生 capability report，禁止修改 core engine 以硬塞本研究。

若可表達，config 必須使用 `schema_version: "strategy_run"`、`workspace/features/` 的 data contract、明確 `fill_model`、`local_research_only: true`，並執行：

```powershell
& .\.venv\Scripts\python.exe scripts\workspace_doctor.py --config workspace\runs\strategy-run-btc-sec-crosscheck.json
```

預期無 `[FAIL]`；有任何 `[FAIL]` 即停止，不跑 full backtest。engine output 與 standalone pandas ground truth 的關鍵欄位差異若超過 0.3 percentage point，標記 mismatch 並解釋 fill timing/cost，不擅自調整結果。commit 只在 cross-check 通過後：`git add workspace/runs workspace/reports/agents/btc_sec && git commit -m "add btc sec lo2cin4bt crosscheck"`。

### 6. 產生 self-contained HTML、Obsidian Markdown 與圖表

新增：

- `workspace/reports/agents/btc_sec/build_report.py`
- `workspace/reports/agents/btc_sec/build_md.py`
- `workspace/reports/agents/btc_sec/test_report_build.py`

`build_report.py` 讀取 CSV/JSON，在 build time 內嵌 SVG（不能以 browser runtime `fetch()` 讀 sibling JSON），至少產生：BTC log price + SEC 3% extreme shading、SEC percentile decile/horizon summary、事件表、資料 provenance、sample-size warning、engine cross-check status。`build_md.py` 產生 YAML frontmatter、引用本地 SVG、列出 real/proxy/stale/not-generated 標籤及不確定性。

驗證：

```powershell
& .\.venv\Scripts\python.exe -m pytest workspace\reports\agents\btc_sec\test_report_build.py -q
& .\.venv\Scripts\python.exe workspace\reports\agents\btc_sec\build_report.py --input-dir workspace\reports\agents\btc_sec
& .\.venv\Scripts\python.exe workspace\reports\agents\btc_sec\build_md.py --input workspace\reports\agents\btc_sec\report.html
```

預期：`report.html`、`report.md`、至少兩個 `.svg` 存在；HTML 不含 `fetch(`；SVG 有 path/polyline 與 signal shading；Markdown 可在無網路時引用本地 SVG。commit：`git add workspace/reports/agents/btc_sec && git commit -m "build btc sec research reports"`。

### 7. 完成驗收與研究結論邊界

執行：

```powershell
& .\.venv\Scripts\python.exe -m pytest workspace\reports\agents\btc_sec -q
& .\.venv\Scripts\python.exe scripts\project_consistency_audit.py
& .\.venv\Scripts\python.exe scripts\indicator_doctor.py workspace\indicators\extensions
```

預期：BTC SEC 專屬 tests 全 pass；consistency/indicator checks 的既有 failure 與本次 failure 分開記錄；沒有把舊 artifact 與新 contract 混用。最後在 `report.md` 和 `report.html` 明確寫：研究只回答第一層統計/部分失效條件，不能證明因果、不能回答「誰在支付」，亦不是投資或交易建議。commit：`git add workspace/reports/agents/btc_sec && git commit -m "validate btc sec research deliverables"`。

## Tests / validation

每個 coding task 遵循 TDD：先新增能精準描述 contract 的 failing test；用指定 pytest 命令確認 failure 原因是缺少 implementation；最小實作後重跑到 pass；每一個可獨立完成的階段 commit。資料下載、完整分析和 HTML build 均必須保存命令、時間、輸入 checksum、輸出路徑與 stderr 摘要。任何 timeout、缺少 PSIP、point-in-time 不明或 engine mismatch 必須保留為明確 blocker，不以 proxy 通過。

## Risks, tradeoffs, and open questions

- **最大 blocker：PSIP。** 若 Bitcoin Magazine Pro CSV 無法取得、內容會 retroactively revise 或缺 publication timestamp，結果只能叫 proxy/limited，不能宣稱驗證歷史 SEC。
- **資料起始日衝突。** prompt 寫 2010-07-19 Binance 上市日，但 Binance 現貨歷史未必覆蓋該日；實作者要記錄實際 effective start，不可補造早期價格。
- **Expanding percentile 定義需固定。** 本計畫採「t 的 signal 只使用 t-1 以前 SEC」，warmup 365 日；若實作改用包含 t，必須視為錯誤並由測試阻擋。
- **重疊 forward returns。** 事件日之間的 30/90/180/365 日回報並非獨立；Welch t-test 與普通 bootstrap 可能低估依賴性，報告須列為限制，不把 p-value 當因果證據。
- **Deflated Sharpe/White reality check。** prompt 要求，但目前 repo 沒有已核對的專用實作；第一版只能完成 12 組 Bonferroni p-value，若要正式 DSR/WRC 必須另開 engine-neutral statistics task，不能改名冒充。
- **2025/2026 事件完整性。** 最近事件的 180/365 日 forward return 可能尚未成熟，表格保留 NaN，不能刪掉或當作 0。
- **leverage proxy。** funding rate/net flow 不是強制平倉賣家本身；若加入，只能標成 proxy，並報告缺失與時間對齊。
- **lo2cin4bt 邊界。** 若目前 schema/registry 不支持外部 PSIP 與這類事件研究，應採 standalone workspace analysis + optional engine cross-check，而不是修改 core folders。
- **未決定的資料源。** 實作者在有資料前不能決定 primary provider；需以實際可取得、可審計且 point-in-time 狀態較清楚者為準，並在 contract 固化後才跑 full analysis。

