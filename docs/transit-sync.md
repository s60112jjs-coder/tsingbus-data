# 清BUS 校外交通同步與發布

使用者已於 2026-10-03 確認發布其他 9 條、暫緩 2011。程式與資料已提交 GitHub，Pages 發布及公開資料比對檢查通過。App 程式碼沒有修改。每日自動同步需使用者先完成 Actions Secrets 設定。

## 使用者會看到的效果

App 的三個目的地為新竹火車站、高鐵新竹站、台北市區。台北市區分為台北轉運站，以及公館／臺大／景美／新店／東區；1728 納入後一組。

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

1. 2011 的白天班距是起站區間。現有 App 能解析 originZh／originEn，但班距畫面沒有顯示該起站說明，直接發布可能被誤認為清大站服務區間。目前已按使用者確認暫緩 2011、發布其他 9 條。之後由 Claude 補上班距起站標示，確認後才能開啟完整 10 條。本次沒有修改 App。
2. TDX Schedule 的 ServiceDay 僅提供 MON–SUN，沒有各業者國定假日與寒暑假例外。既有 App schema 只能全體假日套用 SUNDAY，無法精準表示逐路線例外。本方案使用人事行政總處 2026／2027 行政機關辦公日曆建立假日清單，排除普通週末；83 國定假日停駛已另以業者確認。其餘路線的國定假日套週日是現有 App 規則，不能宣稱已逐條確認業者適用。日曆有效期至 2027-12-31，過期拒絕同步，必須先更新。

來源：TDX Bus Route／StopOfRoute／Schedule；83 業者 https://www.yosemite-bus.com.tw/no81_bus.asp ；1728 官方 https://www.taiwanbus.tw/eBUSPage/Query/QueryResult.aspx?rno=17280 ；日曆 https://data.gov.tw/dataset/14718 。

## GitHub 變更清單

- 新增 scripts/sync_transit.py、scripts/transit-holidays.json、scripts/verify_pages.py。
- 新增 tests/test_sync_transit.py、.gitignore、本說明。
- 新增 .github/workflows/transit-sync.yml、.github/workflows/pages.yml。
- 首次發布新增 docs/v1/transit.json，僅在 docs/v1/manifest.json 登錄 transit 及更新 manifest 發布時間。
- Pages 的發布來源改為 GitHub Actions。原因：GITHUB_TOKEN 的資料提交不會自動觸發既有 Pages 分支建置，所以同步工作明確呼叫 Pages 工作。手動 main/docs 更新仍會發布。既有公告同步工作保留。
- 發布後讀取網站 manifest 和所有登錄 JSON，逐位元組比對當次發布內容；讀取失敗或不一致則工作標示失敗。

使用者自行新增 repository Actions Secrets：TDX_CLIENT_ID、TDX_CLIENT_SECRET。不需要額外 PAT。目前預設同步 9 條，不需額外 Variables。之後確認 App 起站標示完成，才可設定 repository Actions Variable TRANSIT_ORIGIN_FREQUENCY_READY=true 加入 2011。

## 驗證結果

8 項單元測試涵蓋跨午夜、倒序時間拒絕、2011 發布閘門、迴圈站序、校內／路邊站區別、缺路線／業者拒絕、非實質異動不更新、同日兩次實質更新與日曆過期。

實際 App Kotlin 解析器讀取真實資料：10 條路線、3 個分頁、零解析警告；10 組方向查詢、跨午夜、假日與校內站區別檢查通過。首次 Pages 部署已成功，公開 transit 有 9 條，網站 manifest 與所有登錄資料比對通過；Actions 端向 TDX 查詢仍待金鑰設定後實際執行。
