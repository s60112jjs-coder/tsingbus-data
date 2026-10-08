# 清BUS 校外交通同步與發布

## 維護提醒

新增「校外交通維護提醒」Actions：每次校外交通同步完成後檢查結果，另每天台灣時間 05:45 檢查日曆有效期；提醒工作完全不呼叫 TDX，不讀取 TDX Secrets，也不讀取同步工作原始 log。

- 假日日曆 coverageEnd 前 60 天，建立一則 GitHub issue 並指派給 s60112jjs-coder，內容包含官方日曆來源、修改檔案與驗證步驟。目前 coverageEnd=2027-12-31，首次提醒日期為 2027-11-01。相同到期日即使 issue 已關閉，也不重複建立；更新有效期後，下一次到期會有新的提醒。
- 最新完成的 main 同步失敗時建立並指派提醒，附失敗工作連結。同一個未解決問題不每日新增 issue；同步恢復成功時自動關閉未解決的失敗提醒。
- GitHub Notifications 的 Participating／@mentions 郵件通知已確認開啟；Actions 已設為只通知失敗。郵件依 GitHub 投遞與使用者信箱設定送達，提醒本身也會保留在 repository Issues 與 GitHub 通知中心。
- 手動執行可選 dry_run，僅輸出檢查結果，不建立或關閉提醒。沒有新增額外 Secrets。

使用者已於 2026-10-03 確認 App 的 FREQUENCY 起站標示完成並驗證，正式啟用包含 2011 的完整 10 條路線同步。資料端不修改 App 程式碼。每日同步僅從 Actions Secrets 讀取 TDX 金鑰。

2026-10-09 南部線候選增加和欣客運 7500／7513，完整同步為 12 條路線。App 已實作 trips[].serviceExceptions 日期例外，schemaVersion 仍為 1；站點代號、雙向與單向站、支線排除及驗證見 [南部線資料同步](transit-south.md)。使用者確認效果後才發布。

## 使用者會看到的效果

App 的三個目的地為新竹火車站、高鐵新竹站、台北市區。台北市區分為台北轉運站，以及公館／臺大／景美／新店／東區；1728 納入後一組。

新增 SOUTH 資料供 App 設定「回家的公車：南部線」使用；新竹端為和欣客運新竹站，南部端含台南／高雄沿線實際停靠站。台北線仍保留。舊版 App 略過不認得的 SOUTH 分頁。

App 只讀 https://s60112jjs-coder.github.io/tsingbus-data/v1/transit.json 。格式維持現有 schemaVersion 1，manifest 維持 schemaVersion 2。既有校巴、南大、公告等資料維持原內容。

GitHub Actions 每天台灣時間 05:30、17:30 查 TDX，cron 為 `30 21,9 * * *`。排程可能延遲。只查白名單路線，依 Hsinchu／InterCity 分組，共六次資料請求（另有一次驗證請求）；重試會增加用量。手動執行也會使用額度。

資料正常且有實質變更才更新 transit 與 manifest、提交並發布 Pages；無異動不產生 commit。Pages 工作仍可再次發布既有資料。缺路線、業者、站序或班表資料就失敗，保留已發布版本。App 維持既有快取處理。

## 已確認的路線與時刻

以下為 TDX 查詢時資料；每方向的數字為官方班表筆數，並非人工估計清大站時間。所有 STOP_TIME 使用官方站站時刻，沒有用起站時間加分鐘。

- 藍線1區：HSZ0010，新竹客運。HSZ001001 Direction 0 為往返迴圈：火車站 1、清華大學 16、竹中 29、清華大學 43、火車站 56。輸出拆成兩個方向以保留正確站次。主線平日 51、週六／日 40；HSZ0010A1／A2（藍線1區A）各方向每日 3。實際提供 STOP_TIME，並非只有班距。
- 2路：HSZ0020，新竹客運。HSZ002001 Direction 0 清華大學第 15 站；HSZ002002 Direction 1 清華大學第 7 站。確實停清大。平日去 9／回 8，週六／日去 7／回 6。STOP_TIME。2支A 去程未停清大，本次排除該支線。
- 83：HSZ0008，科技之星交通。HSZ000801／02 Direction 0／1：新竹轉運站第 10／11 站；校內台積館、生科館（人社院）、第二綜合大樓、北校門均有正式站站時刻。主線各方向平日 18，B 支線 HSZ0008B1／B2 各方向平日 2，週末無班。A 支線未服務新竹轉運站，排除。業者另明列國定假日停駛。STOP_TIME。
- 182：HSZ0182，國光客運。HSZ018201／02 Direction 0／1，清華大學均第 12 站；高鐵去程第 23／回程第 1 站。各方向每日 22。STOP_TIME。
- 先導公車：HSZ0185，國光客運。正式名稱為先導公車，HSZ018501／02 Direction 0／1，清華大學第 12／23 站，高鐵第 30／5 站，各方向平日 22。先導公車A 為 HSZ0185A1／A2，週六／日各方向 22。STOP_TIME。
- 5608：THB5608，捷乘客運。THB560801／02 Direction 0／1，清華大學第 9／33 站。去程平日 46／六 35／日 36；回程平日 44／六 36／日 36。新竹端包含新竹站與中正路，分別命名，避免混成同一站牌。STOP_TIME。
- 2011：THB2011，豪泰客運。THB201101／02 Direction 0／1，清華大學第 7／5 站。混合 STOP_TIME 與 FREQUENCY：06:00–20:00 班距為起站服務區間；往新竹平日 15 分、週末 10–15 分，往台北每日 10–15 分。夜間固定班次去程平日 10／六 16／日 11，回程平日 8／六 12／日 11。跨午夜依服務日存成 24:xx／25:xx。香山支線排除。
- 1822：THB1822，國光客運。THB182201／02 Direction 0／1，清華大學第 9／5 站。各方向每日 12。STOP_TIME；未停清大的 A 支線排除。
- 9003：THB9003，新竹客運與三重客運聯營。THB900301／02 Direction 0／1，清華大學第 9／5 站。新竹客運各方向週一至四 18／五 26／六 25／日 26；三重各方向週一至四 22／五六日 31。各業者資料獨立配對與驗證。STOP_TIME。
- 1728：THB1728，目前業者為亞聯客運。THB172801／02 Direction 0／1，清華大學第 18／5 站。往台北依序服務中央新村（小碧潭）、大坪林、景美、公館、臺大、仁愛敦化等；各方向週一至四 23／五 25／六 17／日 20。STOP_TIME。

各路線的 Direction 是 TDX 原始方向，不以 0 一律代表離開清大。SubRoute、Operator 與 StopSequence 都參與匹配。App 站點使用穩定英文代號，例如 NTHU_NORTH_GATE（光復路清華大學站）、NTHU_CAMPUS_NORTH_GATE（83 校內北校門）、HSR_HSINCHU、TAIPEI_BUS_STATION；不將 TDX StopUID 當公開站點 id。

## 必須了解的兩項限制

1. 2011 的白天班距是起站區間。App 已完成並驗證 FREQUENCY 的 originZh 起站標示，例如「台北轉運站發車：約 10～15 分一班，到 20:00」。同步保留起站名稱與官方班距，夜間保留官方 STOP_TIME，絕不推估清大站時刻。workflow 一律使用 --origin-frequency-ready，不再使用開關或 --skip-2011。
2. ServiceDay 為 MON–SUN，但 TDX 的南部線 Schedule 另提供逐班 SpecialDays 日期例外，必須保留為 serviceExceptions，不能一律宣稱 TDX 沒有例外。App 未命中日期例外時，才沿用全體假日套 SUNDAY。本方案使用人事行政總處 2026／2027 行政機關辦公日曆建立假日清單，排除普通週末；83 國定假日停駛已另以業者確認。既有 10 條路線的例外同步邏輯不在此次南部線變更範圍；其國定假日套週日不能宣稱已逐條確認業者適用。日曆有效期至 2027-12-31，過期拒絕同步，必須先更新。

來源：TDX Bus Route／StopOfRoute／Schedule；83 業者 https://www.yosemite-bus.com.tw/no81_bus.asp ；1728 官方 https://www.taiwanbus.tw/eBUSPage/Query/QueryResult.aspx?rno=17280 ；日曆 https://data.gov.tw/dataset/14718 。

## GitHub 變更清單

- 新增 scripts/sync_transit.py、scripts/transit-holidays.json、scripts/verify_pages.py。
- 新增 tests/test_sync_transit.py、.gitignore、本說明。
- 新增 .github/workflows/transit-sync.yml、.github/workflows/pages.yml。
- 首次發布新增 docs/v1/transit.json，僅在 docs/v1/manifest.json 登錄 transit 及更新 manifest 發布時間。
- Pages 的發布來源改為 GitHub Actions。原因：GITHUB_TOKEN 的資料提交不會自動觸發既有 Pages 分支建置，所以同步工作明確呼叫 Pages 工作。手動 main/docs 更新仍會發布。既有公告同步工作保留。
- 發布後讀取網站 manifest 和所有登錄 JSON，逐位元組比對當次發布內容；讀取失敗或不一致則工作標示失敗。

使用者自行新增 repository Actions Secrets：TDX_CLIENT_ID、TDX_CLIENT_SECRET。不需要額外 PAT。南部線發布後一律同步完整 12 條，不需要任何 2011 開關 Variable；既有 workflow 仍使用 --origin-frequency-ready，排程不變。

## 驗證結果

8 項單元測試涵蓋跨午夜、倒序時間拒絕、2011 發布閘門、迴圈站序、校內／路邊站區別、缺路線／業者拒絕、非實質異動不更新、同日兩次實質更新與日曆過期。

實際 App Kotlin 解析器讀取真實資料：10 條路線、3 個分頁、零解析警告；10 組方向查詢、跨午夜、假日與校內站區別檢查通過。2026-10-03 完整 10 條路線已實際驗證成功：GitHub Actions 從 Secrets 取得金鑰並向 TDX 查詢，提交 transit／manifest，Pages 發布及所有登錄資料比對通過。公開 transit.json 包含 2011，並同時具有 FREQUENCY 與 STOP_TIME；兩端 FREQUENCY 起站分別為臺北轉運站、新竹轉運站。

2026-10-03 使用者設定 Repository Secrets 後，[實際同步 run 37114784487](https://github.com/s60112jjs-coder/tsingbus-data/actions/runs/37114784487) 的 sync 與 publish / deploy 均成功。網站 manifest 的 transit.updatedAt 為 2026-10-03T17:57:42+08:00。先前缺少金鑰的失敗已解除。
