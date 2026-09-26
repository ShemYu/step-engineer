# Step Engineer：繁體中文說明

[English README](../README.md) · [主 Agent 接法](integrations.md) · [委派指示](parent-agent-instructions.md) · [真實案例](case-study.md)

Step Engineer 是在本機執行的工程最佳化 sub-agent，使用 **Step-5-Preview**。主 Agent 保留既有模型與推理設定，例如支援時使用 Ultra；它負責需求、驗收與最終採用。Step worker 接收有界任務，在副本裡修改、測試、量測，交回 patch 與證據，不會替換主 Agent、自動套用 patch 或發布修改。

預設是 `medium`、每次最多 **16,384 輸出 tokens／300 秒**、全程最多 **250,000 tokens**。這是目前可用的起點，不是成功保證。本次一個真實任務中，high 配合 8,192 與 16,384 輸出上限的兩次嘗試都未產生 patch；medium 一次產生通過驗收的版本。單一案例不能證明 medium 普遍優於 high。

## 環境需求

- **macOS 與 `/usr/bin/sandbox-exec`**。其他平台拒絕執行候選程式，沒有自動退回無隔離模式。
- Python **3.11+**；建議使用已驗證的 **3.12**。
- [uv](https://docs.astral.sh/uv/)。
- 真實模型工作需要 Step API key、模型存取權與足夠額度。

隔離器支援安裝中的 Python runtime 與有限系統路徑。其他 runtime／compiler 可能需要額外設定；先驗證工具鏈，不要停用隔離來繞過問題。

## 先跑不需要 key 的範例

先取得 repository，再執行範例：

```sh
git clone https://github.com/ShemYu/step-engineer.git
cd step-engineer
uv sync --frozen --python 3.12
uv run step-engineer run examples/batch_aggregation/job.json --offline-demo
```

這會使用真實 harness 與 sandbox，但解答是**人工預寫的 scripted solution**。它驗證執行流程，不能當作 Step 模型效能成果。[範例說明](../examples/batch_aggregation/README.md)列出完整行為契約。

## 設定真正的 Step 工作

```sh
cp .env.example .env.local
chmod 600 .env.local
```

在本機編輯 `.env.local`，將下列占位文字換成自己的 key：

```dotenv
STEP_API_KEY=YOUR_STEP_API_KEY
STEP_BASE_URL=https://api.stepfun.ai/v1
```

不要 commit 此檔、把 key 貼進 prompt，或把憑證加入 `job.files`。也支援 fallback 變數 `STEPFUN_API_KEY`；既有程序環境的值優先於 `--env-file`。Base URL 僅接受已確認的官方 Step endpoint。

```sh
uv run step-engineer --env-file .env.local doctor
uv run step-engineer --env-file .env.local run examples/batch_aggregation/job.json
```

`doctor` 只檢查本機設定與隔離器是否可用，不驗證認證、額度或模型存取。**Live job 會把選定的可見原始碼與工具回饋送到 StepFun，並可能產生費用。**

範例使用 medium，最多 12 次模型請求、24 次工具呼叫、全程 600 秒／250,000 tokens、每次 300 秒／16,384 輸出 tokens、保守估算 US$0.50。一般 JobSpec 預設則為 40 次工具呼叫與 US$1；其他主要上限相同。

## 接上 GPT、Grok 或 Claude

由本機 MCP host 啟動 stdio server：

```sh
uv run --project /absolute/path/to/step-engineer step-engineer \
  --env-file /absolute/path/to/private/step.env \
  --runs-dir /absolute/path/to/optimization-runs \
  serve --allow-root /absolute/path/to/your-project
```

以上都是占位路徑。每個允許的專案分別指定 `--allow-root`；省略時只允許隨附範例。Server 不開放 HTTP port。

| 工具 | 用途 |
| --- | --- |
| `submit_optimization(job)` | 快速提交並取得 run ID |
| `get_optimization_status(run_id)` | 查進度、狀態與估算費用 |
| `get_optimization_result(run_id)` | 讀量測、最終驗收與產物路徑 |
| `cancel_optimization(run_id)` | 取消本機工作 |

工作期間必須保持同一個 MCP session。Server 關閉會取消進行中的工作；重啟不會自動續跑或重新呼叫模型。

GPT、Grok、Claude 可以是主模型，但**工具必須由有權存取檔案的本機應用程式執行**。雲端模型不能直接存取這台 Mac 的檔案或 localhost。已有三種 provider 格式的 Python adapter 與離線測試；不宣稱完成三家主模型各自的付費端到端驗證。完整範例見 [integrations](integrations.md)。

## 撰寫工作契約

複製 [example job](../examples/batch_aggregation/job.json)，並查看 schema：

```sh
uv run step-engineer schema
```

- `source_dir`：CLI 相對於 job JSON 所在目錄解析；MCP 必須使用絕對路徑。
- `files`／`editable_files`：明列要複製與可修改的既有 UTF-8 檔案；拒絕資料夾、symlink、隱藏檔與路徑穿越。
- `objective`：寫清楚行為、目標與不能犧牲的條件。
- `checks`／`benchmark`：由主 Agent 擁有的固定功能檢查與量測命令，採 argv，不經 shell 展開。
- `final_only_files`／`final_checks`：獨立驗收資料與命令，開發階段不提供給 Step；真實工作建議設定。
- `metric`／`direction`／`constraints`：指標、優化方向、每次量測都必須滿足的限制。
- `repetitions`／`minimum_relative_improvement`：重複次數與最小改善幅度，使用中位數比較。
- `reasoning_effort`／`budget`：worker effort 與請求、工具、token、時間、估算費用、無改善次數上限。

`{python}` 使用已安裝的 Python；`{workspace}` 與 `{scratch}` 是隔離目錄。命令執行時 workspace 唯讀，編譯產物與暫存寫入 scratch。其他工具鏈需先驗證可用性。

外部 runner 的 `elapsed_seconds` 包含啟動、資料建立與清理成本。可信任 benchmark 可在最後一行提供 JSON metrics；stdout 無法覆寫外部耗時。缺少指標、非有限值、檢查失敗、逾時或輸出／儲存超限都會拒絕該次量測。自行輸出的分數仍需要可信任評測設計。

## 預算、最佳版本與驗收

單次 deadline 同時受到 `max_request_seconds`（預設 300，可設 5–600）及全局剩餘時間扣除驗收保留時間限制。Token 與估算費用使用請求前保留額，可能在表面上限前停止。輸出上限包含 reasoning tokens，不只可見答案。

費用採 2026-09-26 查核的輸入 US$1/M、輸出 US$2.70/M，忽略快取折扣。這是本機保守估算，**不是帳單保證**。取消或逾時仍可能被計費；程式標示不確定性，不自動重試。

只有通過檢查且量測更好的候選會成為 `best`。最終驗收從這個已保存版本重新建立副本。**最後一次未量測的寫入不會覆蓋最佳版本。** 因此要分開看停止原因與驗收結果：預算用完時，先前的最佳版本仍可能通過最後驗收。

| 產物 | 意義 |
| --- | --- |
| `result.json`／`report.md` | 狀態、量測、用量與驗收 |
| `accepted.patch` | 最佳版本通過最終驗收後才含修改 |
| `best-development.patch` | 僅供診斷，不能當作驗收通過 |
| `source-manifest.json` | 原始檔 hashes，套用前檢查來源是否變動 |
| `evaluations.json`／`events.jsonl` | 量測與事件紀錄 |

產物預設放在目前工作目錄的 `runs/<run_id>/`；接入 host 時明確指定 `--runs-dir`。一起檢查 `accepted`、`final_validation` 和 `stop_reason`。未設定獨立 `final_checks` 時，仍重跑一般檢查與 benchmark，但 `independently_checked=false`。原始目錄不被修改，套用 patch 由主 Agent 負責。

## 隔離與資料界線

只選可分享給 StepFun、與任務相關的原始碼與測試回饋。不要把敏感內容藏在一般程式檔裡。Final-only 檔案不提供給 worker 的開發工具，但最終驗收時，被測程式可以讀到它們。

Sandbox 禁止網路、限制讀檔並防止寫入命令 workspace；子程序使用不含 API key 的乾淨環境。每個輸出 stream 上限 16 KiB、scratch 單檔 16 MiB、總量 64 MiB 為週期監測限制，命令結束清除 scratch。

這是個人本機工程工具，不是 VM 或供陌生人執行任意程式的服務。逃離 process group、同一 interpreter 內篡改評測等情況需要更強隔離。原始碼副本、patch、報告與測試輸出也可能包含私人資料，分享前要檢查。Raw reasoning 僅保留於記憶體以延續工具呼叫，不寫入報告。

## 開發驗證

```sh
uv sync --frozen --python 3.12
uv run pytest -q
uv run ruff check src tests
```

測試涵蓋 HTTP mock、harness 狀態、路徑界線、真實 macOS sandbox 與 MCP stdio。測試通過證明框架行為，不能代替特定任務的真實模型評估。

## 授權

[MIT](../LICENSE)。案例提到的私人應用程式素材不包含在此 repository，也不由此授權。
