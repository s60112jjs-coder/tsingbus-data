# 校外交通：自動同步、異常修復與營運異動監測（2026-10-26）

首要原則：**寧可保留最後一版正確班表並標示「資料可能過期」，也不自動發布錯誤班次。**
重試只用來處理暫時性問題，永遠不放寬任何驗證。

## 1. 1728 同步失敗（2026-10-25 起）的診斷

- 失敗紀錄：run 40143058218（10/25 07:31）與 40199409995（10/25 21:49），兩次都是 `Sync rejected: Missing required route 1728`。
- 兩次的「查詢並驗證官方靜態資料」都跑了約 80 秒＝六次 TDX 請求全部有回應（每次間隔 15 秒）。逾時與 HTTP 錯誤可以排除；問題出在 **TDX 的回應裡沒有 THB1728 的 Route、StopOfRoute 或 Schedule**。
- 前兆：最後一次成功（10/24 07:54）時，1728 的班次從 41／38 班驟減成 26／26 班，有些班次只剩「週一」或「週一、週日」。
- 背景：公路局已廢止亞聯客運 1728 的路線許可並公開徵求新業者，亞聯目前是代駛（[工商時報](https://www.ctee.com.tw/news/20250628700722-431401)、[遠見](https://city.gvm.com.tw/article/122407)）。換業者時 TDX 常會先下架舊資料或改 RouteUID。
- 原本的驗證**擋得正確**：缺路線就拒收，保留上一版。問題在於「一條路線缺漏就讓其他 13 條也停止更新」，而且 App 看不出 1728 是舊資料。
- 本機沒有 TDX 金鑰，無法直接確認是哪個端點缺資料、或是否已改 RouteUID。新版同步在缺路線時會多做一次 `RouteName/Zh_tw eq '1728'` 查詢，把結果寫進 `transit-status.json` 的 `diagnosis`（`ROUTE_UID_CHANGED`／`ROUTE_NOT_LISTED`／`PARTIAL_RESPONSE`），下一次排程就會知道答案。

另外發現：10/15 起幾乎所有路線每天都有 1～2 分鐘的中途站時刻變動（起站時間不變），每天都會產生一個資料 commit。這是 TDX 端的資料，沒有自動消除，只在此記錄。

## 2. 同步流程（每天 05:30／17:30，頻率不變）

1. 跑全部單元測試。
2. 取得 TDX 資料。暫時性錯誤（逾時、429／5xx、認證伺服器異常、空回應）在單次請求內已重試 3 次；整輪仍失敗時，**5 分鐘後再完整跑第二輪**。
3. 嚴格驗證（站序、StopUID、業者、支線、日期例外…，規則與原本相同）。
4. **單一路線整條消失**（最多 2 條）：其他路線照常更新；消失的路線保留最後一次驗證通過的那份，`transit-status.json` 標成 `STALE_DATA`。超過 2 條、或該路線從來沒有發布過，就整份拒收。
5. **班次驟減**（少於上一版的一半，且上一版至少 4 班）：同樣保留上一版、標 `SUDDEN_TRIP_DROP`，並立刻通知。
   **某個星期整天消失**（上一版那天有班、新資料一班都沒有）：保留上一版、標 `SERVICE_DAY_LOST`，立刻通知。10/24 的 1728 就是這種情況（只剩週一、週日），原本的規則沒擋下來。確認官方真的減班後，手動執行同步並在 `accept_trip_drop` 填路線 id。
6. 路線代號改名、業者不符、站點未審核等「規格變更」：**不重試、不猜測**，整份拒收並通知。
7. 有實質異動才 commit。Git 衝突：不 force push，改成重新取最新 main、把已驗證的候選資料重新套用，最多 3 次。
8. 發布 Pages（原本就有立即比對）→ **約 5 分鐘後再讀一次公開網站**，逐位元組比對 manifest 與所有登錄檔案。不一致就自動重新發布一次，再等 5 分鐘複檢；仍失敗才算失敗。
9. 同步連續失敗超過 30 小時，`transit-status.json` 的 `feed` 會標成 `STALE_DATA`（只在狀態改變時 commit）。同步恢復後自動清除。

`transit.json` 裡人工加的 `suspensions` 不會再被同步洗掉（原本會）。

## 3. 營運異動監測（每 2 小時）

來源與可信度：

| 來源 | 用途 | 可以把路線標成 |
|---|---|---|
| TDX `Bus/Alert/InterCity`、`Bus/Alert/City/Hsinchu`（營運通阻） | 官方逐路線、方向、班次的異動 | SUSPENDED、PARTIAL_SUSPENSION、SERVICE_ALERT、NORMAL |
| 人事行政總處 [天然災害停止上班及上課情形](https://www.dgpa.gov.tw/typh/daily/nds.html) | 風險提示 | 只有 UNCONFIRMED |

TDX 另有 `Bus/News/*`（最新消息），是自由文字、無法可靠對應路線，**不拿來判斷狀態**。中央氣象署颱風警報需要另外申請授權碼，這次沒有接。

判斷規則：

- 以「路線＋方向＋班次＋業者＋時間」為單位。只列出部分班次、單一方向、某條支線、或聯營路線只有一家業者停駛 → `PARTIAL_SUSPENSION`，不會變成整條停駛。
- 新竹市公車只看新竹市的通阻資料，公路客運只看 InterCity；182（市區）與 1822（國道）不會互相誤配。
- `Status` 與 `Effect` 互相矛盾（例如「全部營運正常」卻「班次取消」）→ 只標 `SERVICE_ALERT`，加 `conflict: true` 並通知人工。
- 停班停課只對「整個縣市」的宣布有效，某鄉某校的局部停課略過。每條路線依經過的縣市判斷（例如 7513 看新竹市、臺南市、高雄市）。**停班停課永遠不會讓班次被取消**，只會顯示「營運待確認」。
- 某路線某天已經有官方公告（包括官方確認正常），那天就不再顯示停班停課的提示。
- **沒有公告＝沒有發現異動**，`routes` 裡不會出現；只有官方公告 `Status=1` 才會是 `NORMAL`。

自動解除：

- 公告從 TDX 消失（撤回）→ 下一次檢查就移除。
- 超過 `endTime` → 移除。
- 沒有 `endTime` 的公告：開始後 24 小時（`expiresAt`）起，`SUSPENDED` 降為 `SERVICE_ALERT`，不會永久停駛。
- 停班停課提示過了那一天就移除。
- 來源暫時失敗：保留尚未過期的舊內容、該來源標 `UNAVAILABLE`，`validUntil` 不延長。超過 `validUntil`（最後成功後 30 小時）App 應視為「營運資訊無法確認」。

寫入頻率：內容改變才寫；沒變時每 12 小時寫一次心跳（更新 `validUntil`），讓 App 分得出監測還活著。

## 4. 狀態模型

| 狀態 | 意義 | 來源 |
|---|---|---|
| `NORMAL` | 官方明確公告正常營運 | TDX 通阻 Status=1 |
| `SUSPENDED` | 官方確認整條（該時段）停駛 | TDX 通阻 Status=0 或 Effect=4，且範圍是整條路線 |
| `PARTIAL_SUSPENSION` | 部分方向／班次／業者停駛 | 同上，但範圍有限 |
| `SERVICE_ALERT` | 有異動（減班、改道、延誤、資料矛盾），無法逐班判定 | TDX 通阻其他 Effect |
| `UNCONFIRMED` | 沿線縣市停班停課，但業者沒有公告 | 人事行政總處 |
| `STALE_DATA` | 顯示的班表落後於官方最新資料 | `transit-status.json`（同步程式） |
| （沒有列出） | 沒有發現異動，照原定班表 | — |

## 5. 檔案

- `docs/v1/transit-status.json`（同步寫入，[schema](schema/transit-status.schema.json)），manifest key `transitStatus`。
- `docs/v1/transit-alerts.json`（監測寫入，[schema](schema/transit-alerts.schema.json)），manifest key `transitAlerts`。
- 兩個檔案分開，是為了讓兩個工作各寫各的，不會互相衝突。`transit.json` 的欄位完全沒有改。

`transit-status.json` 範例（1728 缺漏時）：

```json
{
  "schemaVersion": 1,
  "updatedAt": "2026-10-26T05:31:10+08:00",
  "feed": null,
  "routes": {
    "1728": {
      "state": "STALE_DATA",
      "reason": "SOURCE_MISSING",
      "since": "2026-10-26T05:31:10+08:00",
      "dataAsOf": "2026-10-24T07:54:42+08:00",
      "noteZh": "官方資料暫時缺少這條路線，顯示的是最後一次驗證成功的班表，可能與實際營運不符。",
      "noteEn": "Official data is temporarily missing this route; showing the last verified timetable, which may be outdated.",
      "diagnosis": {"missingEndpoint": "ROUTE", "diagnosis": "ROUTE_NOT_LISTED", "foundRouteUIDs": [], "foundOperators": []}
    }
  }
}
```

`transit-alerts.json` 範例（節錄，模擬 10/23 颱風：7513 業者公告停駛、1822 一班取消、7500 只有停班停課）：

```json
{
  "schemaVersion": 1,
  "updatedAt": "2026-10-22T20:00:00+08:00",
  "lastCheckedAt": "2026-10-22T20:00:00+08:00",
  "validUntil": "2026-10-24T02:00:00+08:00",
  "sources": [
    {"id": "TDX_BUS_ALERT_INTERCITY", "url": "https://tdx.transportdata.tw/api/basic/v2/Bus/Alert/InterCity", "state": "OK", "lastSuccessAt": "2026-10-22T20:00:00+08:00"},
    {"id": "TDX_BUS_ALERT_HSINCHU", "url": "https://tdx.transportdata.tw/api/basic/v2/Bus/Alert/City/Hsinchu", "state": "OK", "lastSuccessAt": "2026-10-22T20:00:00+08:00"},
    {"id": "DGPA_CLOSURES", "url": "https://www.dgpa.gov.tw/typh/daily/nds.html", "state": "OK", "lastSuccessAt": "2026-10-22T20:00:00+08:00"}
  ],
  "alerts": [
    {"id": "TDX_BUS_ALERT_INTERCITY:A1", "sourceId": "TDX_BUS_ALERT_INTERCITY", "alertId": "A1", "title": "颱風停駛",
     "description": "", "department": "和欣客運", "status": 0, "cause": 6, "effect": 4,
     "url": "https://tdx.transportdata.tw/api/basic/v2/Bus/Alert/InterCity",
     "publishTime": "2026-10-22T19:00:00+08:00", "startTime": "2026-10-23T00:00:00+08:00", "endTime": "2026-10-23T23:59:00+08:00",
     "expiresAt": "2026-10-23T23:59:00+08:00", "firstSeenAt": "2026-10-22T20:00:00+08:00", "sourceUpdateTime": null,
     "routes": {"7513": {"state": "SUSPENDED"}}}
  ],
  "closureHints": [{"date": "2026-10-23", "cities": ["嘉義縣", "屏東縣", "新竹市", "臺南市", "高雄市"], "pageUpdatedAt": "2026-10-22T18:56:03+08:00"}],
  "routes": {
    "7513": [{"state": "SUSPENDED", "startTime": "2026-10-23T00:00:00+08:00", "endTime": "2026-10-23T23:59:00+08:00",
              "expiresAt": "2026-10-23T23:59:00+08:00", "alertIds": ["TDX_BUS_ALERT_INTERCITY:A1"]}],
    "1822": [{"state": "PARTIAL_SUSPENSION", "startTime": "2026-10-23T00:00:00+08:00", "endTime": "2026-10-23T23:59:00+08:00",
              "expiresAt": "2026-10-23T23:59:00+08:00", "alertIds": ["TDX_BUS_ALERT_INTERCITY:A2"],
              "directions": [0], "trips": [{"direction": 0, "departure": "07:00"}]}],
    "7500": [{"state": "UNCONFIRMED", "date": "2026-10-23", "cities": ["新竹市", "臺南市", "高雄市"],
              "noteZh": "新竹市、臺南市、高雄市已宣布停止上班或上課，客運業者尚未公告是否停駛；以下為原定班表，搭車前請向業者確認。",
              "noteEn": "Work/school closure announced in Hsinchu City, Tainan City, Kaohsiung City; the operator has not announced suspensions. Scheduled times shown; confirm before travelling.",
              "sourceUrl": "https://www.dgpa.gov.tw/typh/daily/nds.html"}]
  }
}
```

## 6. App 相容性與降級

- 已上架的 App（`looksValid` 對不認得的檔名回傳 true）會照常下載這兩個新檔、放進快取但不使用，**不影響任何畫面與班表**。兩個檔都很小，只有內容改變或 12 小時心跳時 manifest 才會變。
- `transit.json` 格式不變（`schemaVersion` 仍是 1、沒有新增欄位）。保留下來的舊路線就是上一版原封不動的物件。
- 舊版 App 看不到「資料可能過期」與「營運待確認」，會跟現在一樣照班表顯示。
- 目前 App **不會**因為 `transit-alerts.json` 自動隱藏班次。官方確認停駛時，系統開 Issue 通知，由人工確認公告後在 `transit.json` 的 `suspensions` 加入（App 已支援）。等 App 端支援新檔、並用真實颱風資料驗證過對應規則後，再考慮自動化。

## 7. 通知（GitHub Issue，同一事件只開一次，解決後自動關閉）

| 情況 | 何時通知 |
|---|---|
| 同步工作失敗（已自動重試兩輪仍失敗、資料錯誤、規格變更、推送失敗、發布後複檢失敗） | 該次工作失敗；Issue 會寫出失敗步驟與處理方式 |
| 某條路線暫用舊班表 | 持續 10 小時以上（＝連續兩次排程）；改 RouteUID 或班次驟減則立刻 |
| 整份資料超過 30 小時沒同步成功 | 立刻 |
| 官方公告停駛／部分停駛，或公告欄位矛盾 | 立刻（每則公告一個 Issue，公告結束或撤回後關閉） |
| 監測工作失敗、或監測資料過期 | 立刻 |

正常同步、無異動、自動重試成功、正常複檢都不通知。

## 8. 用量

- TDX：同步每次 6＋1（驗證）個請求，與原本相同；只有失敗時才有第二輪，只有路線消失時才多 1～2 個診斷請求。監測每 2 小時 2 個請求＋1 次認證，約每天 36 次。
- GitHub Actions：同步有異動時多一個約 6 分鐘的複檢工作（大部分時間在等待）；監測每次約 1 分鐘、每天 12 次；通知工作每次監測後跑一次（只呼叫 GitHub API）。公開 repository 不計費。
- Commit：同步只在班表或狀態改變時；監測只在內容改變或每 12 小時心跳時。
