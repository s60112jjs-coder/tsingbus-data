# 南部線資料同步

本機驗證日期：2026-10-09。資料來源為 TDX 公路客運 Route、StopOfRoute、Schedule；schemaVersion 維持 1，App 已提供選用的 trips[].serviceExceptions 日期例外欄位。

## 範圍與站點

僅新增和欣客運（OperatorID 25、HoHsinBus）的 THB7500／THB7513。兩條均保留新竹往南部、南部回新竹；臺北轉運站、三重、經國轉運站與臺中朝馬不列入 SOUTH 方向或目的地。App 只讀 GitHub Pages，沿用每天台灣時間 05:30／17:30 的同步，不新增 Secrets，也不增加資料端每次正常同步的六次白名單資料請求。

公開站點代號不使用 TDX StopUID；上線後不可任意變動。

| 固定代號 | 官方站名／顯示名稱 | 目前可查方向 |
| --- | --- | --- |
| HOHSIN_HSINCHU | 和欣客運新竹站（TDX 名稱：新竹站） | 新竹端，side=CAMPUS |
| XINYING | 新營站 | 雙向 |
| MADOU | 麻豆站轉運站 | 雙向 |
| YONGKANG_HOHSIN | 永康轉運站 | 雙向 |
| LIUJIADING_HOHSIN | 六甲頂站 | 新竹往南部 |
| TAINAN_HOHSIN | 臺南轉運站 | 雙向 |
| NANZI | 楠梓站 | 雙向 |
| JIURU_HOHSIN | 九如站 | 南部回新竹 |
| KAOHSIUNG_HOHSIN | 建國客運站 | 雙向 |
| ZHONGZHENG_HOHSIN | 中正站 | 南部回新竹 |
| LINGYA_SPORTS_PARK | 捷運苓雅運動園區站 | 新竹往南部 |

目的地依 TDX 站點緯度由北到南排列。方向內則完全依官方 StopSequence 排列，因此高雄市內的站序不一定與目的地清單相同。沒有反向服務的站不可編出反向班次。

HOHSIN_HSINCHU 為和欣路線專用映射；不得把 5608 的「新竹站」改成這個代號。App GPS 既有代號與座標不修改。新竹站官方網頁地址為金城一路35巷13號，App 原規格地址不同，這次不修改地圖。

## 支線與逐班篩選

- 7500：已審核含新竹的基本、D、F、O、T 雙向支線。此次有可用新竹時刻的為 D1／D2、F1／F2、T1／T2，共 106 筆正規化班表；其中 11 筆帶日期停駛例外。O1／O2 只有站序、沒有 Schedule，不能編出班次。
- 7513：已審核含新竹的基本、B、D、F、I 雙向支線；此次共 123 筆正規化班表，其中 16 筆帶日期停駛例外。
- 229 筆是帶星期條件的資料筆數，並非每日班次數。實際某一天仍須套用日期例外與星期規則。
- 不停新竹的支線全部排除。新出現而未審核的含新竹支線或站名會拒絕同步，保留上一版資料待審核。
- THB750001／THB750002 的兩筆原始班次：StopOfRoute 列有新竹，但 StopTimes 只列到朝馬／經國等其他站，沒有新竹時刻。這不是只有起站時間，先排除待查；日後若 TDX 提供完整有效新竹時刻才可納入。
- 所有納入的實際班次此次均為 STOP_TIME。未來若官方確實只給單一原始起站時刻，使用 ORIGIN_DEPARTURE_ONLY 並保留真正的 originZh／originEn，不換算新竹時刻。多站部分時刻不能任意降成起站時間。
- Route、SubRoute、Direction、Operator 與 StopTime 的 StopUID／StopSequence 必須匹配。7500 Direction 0 為北上、1 為南下；7513 Direction 0 為南下、1 為北上，不能一律假設 0 為離開新竹。
- F1／F2（7500）、B1／B2（7513）為必要核心支線；缺一方向、核心班表或整條路線，拒絕覆蓋已發布 JSON。可選支線沒有 Schedule 時不創造班次。

## 日期例外

TDX SpecialDays.Dates 轉為單日區間，DatePeriod 轉為含起訖日的區間。正規化合併重複、重疊及相鄰的相同結果區間，排序後輸出：

```json
"serviceExceptions": [
  {"startDate": "2026-10-09", "endDate": "2026-10-11", "runs": false}
]
```

此次官方資料均為 ServiceStatus 0（未營運），對應 runs:false。Description 不參與判斷。資料端對其他尚未查證的 ServiceStatus 拒收，不擅自猜測 runs:true，也不丟棄例外；App 本身已能處理 runs:true。

例外對原始服務日期生效，不能改用 24:xx／25:xx 的到站日期。欄位缺漏、錯誤型別、無效日期或反向區間均使同步失敗；例外失敗不能退回星期班表。國定假日僅在沒有命中例外時沿用 SUNDAY。

此次來源 ServiceDay 沒有兩條南部線的週一班次；7500 的週二基本班次又屬缺少新竹時刻的排除資料。這是「TDX 此次沒有可交付班次」，不是宣稱業者週一／週二停駛，不另補時間或套用其他天。每日兩次同步會依後續官方資料更新。

## 本機驗證與發布

- 23 項 Python 測試：既有同步與提醒測試，以及新增站點映射、雙向、略過不停新竹支線、真實起站名稱、部分站時刻排除、日期例外正規化、無效例外拒收、缺核心服務拒收、官方 StopTime 身分檢查、跨午夜與六次資料請求檢查。
- 使用 App 現有實際 Kotlin 解析與查詢程式讀取真實候選資料：12 條路線、4 分頁、零解析警告；60 組日期／目的地／雙向查詢通過，並確認四個單向站的反向查詢不會產生班次。
- THB7513F2 範例：建國客運站 12:25、新竹 16:09；10/11 正確排除，10/18 正確恢復。另驗證下班車查詢及跨午夜原服務日停駛。
- 候選資料由一次完整官方查詢產生，既有 10 條路線仍沿用原同步邏輯，官方實質異動照常更新；不把抓取時間放入班次或當成內容異動。
- 純本機預覽不改 GitHub。使用者確認效果後才能發布；正式同步仍由 Actions 使用原本 Secrets，App 不呼叫 TDX。

來源：[TDX](https://tdx.transportdata.tw/api-service/swagger)、[和欣新竹站](https://www.ebus.com.tw/stations/Sinjhu.html)、[7500](https://www.taiwanbus.tw/eBUSPage/Query/QueryResult.aspx?rno=75000)、[7513](https://www.taiwanbus.tw/eBUSPage/Query/QueryResult.aspx?rno=75130)。
