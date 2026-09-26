# 為什麼使用 Step 5 Preview，以及證據支持到哪裡

[繁體中文 README](README.zh-TW.md) · [English evidence](step-evidence.md) · [本地案例紀錄](case-study.md)

**來源查核日期：2026-09-26。** Step Engineer 的定位是針對 Step 整合的工程優化 harness：在約束下執行，依可量測的回饋反覆改進。本文分開呈現廠商展示、API 文件與一個本地實驗；這些資料都不構成對其他模型的普遍領先證明。

設計假設是：先定義必須維持的行為，再量測候選版本、保留通過條件的最佳版本，利用執行回饋決定下一次修改。父代理負責評測器與採用決定。新工作負載是否適用仍需驗證；規則清楚本身不保證優化有效。

## 廠商展示：GPU kernel 優化

以下來自 StepFun 的[官方模型介紹](https://www.stepfun.com/step-5-preview)及[原始結果圖](https://www.stepfun.com/assets/inference-combined-7fkNnlSY.png)。

| 條件 | 廠商公布的設定 |
| --- | --- |
| 任務 | 從初始描述出發，優化 MLA GPU kernel |
| 硬體 | 一張 NVIDIA H100 |
| 固定 shape | Head dimension 512、batch size 1、64 heads、8,192 tokens |
| 預算 | 每次 24 小時 |
| 選擇方式 | 每模型獨立執行四次，報告最佳一次 |
| 回饋 | 執行修改、量測吞吐、捨棄退步版本，從最佳版本繼續 |
| 指標 | 前向與反向合計的實測 TFLOPS，越高越好 |

![廠商 MLA kernel 結果：Step 5 Preview High 508、Claude Opus 5 Max 493、Kimi K3 Max 307、GLM-5.3 Max 286 TFLOPS](assets/step-kernel-results.svg)

| 模型與推理設定 | 公布的最佳 TFLOPS |
| --- | ---: |
| Step 5 Preview — High | 508 |
| Claude Opus 5 — Max | 493 |
| Kimi K3 — Max | 307 |
| GLM-5.3 — Max | 286 |

這是**廠商自測、固定 shape、四次取最佳**，不是本套件量測或通用排名。來源未交代數值精度、正確性容限、baseline 實作及結果變異。圖中保留歷來最佳值，也顯示許多失敗候選。正文稱約 22 小時達峰，但圖上的 Step 峰點看起來約在 17–18 小時；本文因此只主張**24 小時預算下的結果**，不採用精確達峰時間。

同一份[官方介紹](https://www.stepfun.com/step-5-preview)另有 24 小時後訓練資料優化案例：Qwen3-30B-A3B 的 AIME24 正確率由 **53.3% 升至 60.0%，增加 6.7 個百分點**。這是另一個以可量測回饋驅動改進的廠商案例，本專案沒有重現該實驗。

## 本地證據：一個精靈圖合成工作負載

[案例紀錄](case-study.md)保留三次依序進行的嘗試：兩次 `high` 都耗盡輸出額度，未產生 patch；第三次 `medium` 保留的已量測候選通過最終驗證。各次輸出上限、期限與剩餘成本額度不同，不能視為隔離推理設定變因的對照實驗。

![本地精靈圖合成結果：真實素材合成耗時降低 10.57%，合成批次外部程序耗時降低 21.05%，兩者計時範圍不同](assets/local-case-results.svg)

| 量測項目 | Baseline | 接受的候選版本 | 耗時降低 |
| --- | ---: | ---: | ---: |
| 真實素材：重新合成九個姿勢 | 1.340068 ms | 1.198424 ms | 10.57% |
| 合成批次：外部程序總耗時 | 1.088911 s | 0.859693 s | 21.05% |

降幅為 `(baseline − candidate) / baseline`，不代表 FPS 提升。合成批次包含程序啟動、輸入準備、合成及清理；真實素材後續量測交替執行 baseline 與候選版本。兩者計時範圍不同，百分比不可合併。

兩張圖都使用 repo 內的[數值來源資料](data/step-evidence.json)，可從 repo 根目錄執行 `uv run --no-project --with matplotlib==3.10.8 python tools/render_documentation_charts.py` 重新繪製。重畫圖表不等於重現實驗。

被接受的 run 使用 **126,365 tokens、292.522 秒**，包含八次模型請求與十一次工具呼叫。這些用量與耗時只涵蓋該次 run，不是三次嘗試的總和。它最後因總 token 預算停止；較晚寫入但未量測的修改被排除，保存的最佳版本通過獨立最終驗證。案例也保留失敗紀錄與三次合計約 US$0.25212 的成本估算；這不是與供應商核對後的帳單。

正確性檢查涵蓋 160 個開發案例、2,016 個真實素材案例、63 張參考影格，以及 5,500 次獨立合成 full-RGBA 差分比較。它們支持受測候選與行為契約。公開 repo 未附私人應用素材，因此無法公開重現精確的真實素材結果。公開離線示範採用手寫腳本解法，**不是模型效能證據**。此案例沒有跨模型比較、統計信賴區間或整體產品提速主張。

## 官方能力與 harness 的實際範圍

下表是供應商提供的能力，不表示本套件已使用全部能力或驗證其最大規模。

| 官方能力 | 對優化迴圈的用途 | 本套件的界線 |
| --- | --- | --- |
| [1M 上下文、64K 最大輸出](https://platform.stepfun.ai/docs/en/guides/models/step-5-preview) | 容納所選程式與先前回饋 | 文字 worker；job 每次請求最多 16,384 輸出 tokens，未展示百萬 token 工作負載 |
| [函式工具呼叫](https://platform.stepfun.ai/docs/en/api-reference/tool-call) | 透過 host 工具要求修改及量測 | 由本地 host 執行受保護命令；模型不直接存取電腦 |
| [`low`／`medium`／`high`](https://platform.stepfun.ai/docs/en/guides/developer/reasoning) | 在預算內調整 worker 推理力度 | 預設 `medium`；本地嘗試不證明它普遍最佳 |
| [Prompt 快取](https://platform.stepfun.ai/docs/en/guides/developer/prompt-cache) | 重複前綴可能降低成本 | 不保證命中；本地估算不扣快取折扣 |
| [JSON Mode 與 JSON Schema](https://platform.stepfun.ai/docs/en/guides/developer/json-mode) | 約束結構化回覆 | 目前 worker 使用工具呼叫，未要求 `response_format` schema 輸出 |
| [每百萬 tokens：輸入 US$1／快取輸入 US$0.05／輸出 US$2.70](https://platform.stepfun.ai/docs/en/guides/pricing/details) | 支援有預算的嘗試與成本估算 | 推理 tokens 計入輸出費用；估算不是帳單上限 |

預設是**每個 job 600 秒、每次請求 300 秒、總計 250,000 tokens**，其他預算可能使它更早停止。官方的 64K 輸出上限、多模態能力及 24 小時展示，都不是本套件的實際運作設定。可查閱 [job schema](../src/step_engineer/models.py)、[provider client](../src/step_engineer/provider.py)與[範例 job](../examples/batch_aggregation/job.json)。

本套件針對 Step 整合 worker 與預設值；評測方法本身也適用於其他模型。本 repo 沒有消融實驗證明這個方法對 Step 特別有效。查詢調校、排程或模擬優化是需要各自代表性評測器的候選用途，不是上述案例已證明的能力。

## 官方文件導覽

以下直接來源均於 **2026-09-26** 查核。可由[官方文件索引](https://platform.stepfun.ai/docs/llms.txt)開始；模型頁另有快取及結構化輸出指南連結。

| 文件 | 整合前要確認的內容 |
| --- | --- |
| [Step 5 Preview 模型文件](https://platform.stepfun.ai/docs/en/guides/models/step-5-preview) | 模型 ID、模態、上下文與輸出限制 |
| [Quickstart](https://platform.stepfun.ai/docs/en/quickstart/overview) | Endpoint 與基本請求範例 |
| [Chat Completions API](https://platform.stepfun.ai/docs/en/api-reference/chat/chat-completion-create) | 請求欄位、結束原因與 token 用量 |
| [Tool Call](https://platform.stepfun.ai/docs/en/api-reference/tool-call) | 工具 schema 與 host 整合 |
| [推理最佳實務](https://platform.stepfun.ai/docs/en/guides/developer/reasoning) | 推理力度與回應欄位 |
| [Prompt 快取](https://platform.stepfun.ai/docs/en/guides/developer/prompt-cache) | 前綴重用、快取計費與淘汰 |
| [JSON Mode 與 JSON Schema](https://platform.stepfun.ai/docs/en/guides/developer/json-mode) | 格式約束與語意正確性的差別 |
| [價格與速率限制](https://platform.stepfun.ai/docs/en/guides/pricing/details) | 當前價格與帳戶限制 |

官方發布頁由前端渲染；介紹文字透過頁面[載入的公開 JavaScript 資產](https://www.stepfun.com/assets/index-DqYLKNXj.js)查核，並比對原始圖。網站重建後資產網址可能變動。製作本文沒有執行付費推理，也沒有獨立重現廠商實驗。
