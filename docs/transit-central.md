# 中部線候選與來源對照（2026-10-15 已確認）

查詢日期：2026-10-15。使用者已確認全部 29 個站點代號與候選班表，授權發布並驗證 TDX 同步與 Pages；資料端不修改 App 程式碼。

## 交付內容

完整候選 JSON：[transit.json](/private/tmp/transit-central-preview-20261015.json)。逐站機器可讀來源對照：[source-map.json](/private/tmp/transit-central-source-map-20261015.json)。正式資料位置仍為 `docs/v1/transit.json`，schemaVersion 維持 1。

目前候選包含既有 12 條與新中部 2 條，共 14 條路線、5 個分頁。新增站點代號已由使用者確認，上線後不得任意變動；已存在的 NTHU_NORTH_GATE、HSINCHU_BUS_STATION 及其他站點代號不變。

## 重要核對結果

- 1866：RouteUID=THB1866，國光客運（OperatorID 45）；Direction 0 南下、1 北上。主線與 B、C 支線有 Schedule；A1/A2 雖有清大站序，目前沒有 Schedule，不編造班次。
- 1866 主線南下的 7 筆只提供至中清交流道的官方時刻，僅發布已確認的「新竹轉運站→清大→中清交流道」段；不宣稱這些班次有其他台中站時刻。主線北上 5 筆只有台中端多站時刻、沒有清大時刻，先排除，不能降格成只有起站時間。
- 1866 B1/B2（不經科技生活館）與 C2 均停清大，有官方站站時刻；共連同上述南下段形成 40 筆資料，不是每天 40 班。
- 9010：RouteUID=THB9010，新竹客運（13）與台中客運（56）聯營，兩業者各別配對 StopOfRoute/Schedule；Direction 0 北上、1 南下，共 124 筆資料，不是每天 124 班。
- 9010 北上從「臺中車站(大智北路)」出發，停「朝馬站」；南下終點是「臺中車站(民族路口)」，停「朝馬(臺灣大道)」。必須分開代號，不合併成同一實體站位。
- 本次 TDX Route/StopOfRoute/Schedule 沒有 9010A／9010C，不能自行加入。
- 1866A 另有「朝馬站(國光)」站序；因無 Schedule，不放進這次 29 個可用目的地。暫預留草稿代號 CHAOMA_KUOKUANG，未發布、未當成可搭班次。
- 實際納入的全部 164 筆均為 STOP_TIME，沒有估算時刻。日期例外保留至 trip.serviceExceptions；1866 C2 的 2026-10-24～26 停駛已正規化保留。
- 部分站僅單向有班次；不以另一方向站位冒充，也不編造反向班次。

## 台中端固定代號（已確認）

依此次官方站點緯度由北至南固定排序；後續 GPS 微幅修正不改順序，不製造無意義更新。方向內仍按官方 StopSequence。台中端共 29 個有可交付班次的目的地，不只規格預期的 4 個主要站。

| 官方站名 | 固定代號 | 現有方向 | 路線 |
| --- | --- | --- | --- |
| 中清交流道 | `ZHONGQING_INTERCHANGE` | 南下 | 1866 |
| 水湳轉運中心 | `SHUINAN_TRANSFER` | 雙向 | 1866、9010 |
| 貿易三村(中清路) | `MAOYI_SAN_CUN` | 南下 | 1866 |
| 黎明僑大三街口站 | `LIMING_QIAODA_3RD` | 南下 | 9010 |
| 頂陳平 | `DINGCHENPING` | 南下 | 1866 |
| 陳平 | `CHENPING` | 南下 | 1866 |
| 西屯派出所 | `XITUN_POLICE` | 南下 | 9010 |
| 水湳站(大德國中) | `SHUINAN_DADE_JHS` | 南下 | 1866 |
| 水湳站 | `SHUINAN_STATION` | 北上 | 1866 |
| 捷運文心中清站(中清路) | `WENXIN_ZHONGQING_MRT` | 南下 | 1866 |
| 朝馬(臺灣大道) | `CHAOMA_TAIWAN_BLVD` | 南下 | 9010 |
| 朝馬站 | `CHAOMA` | 北上 | 9010 |
| 曉明女中 | `XIAOMING_GIRLS_HS` | 南下 | 1866 |
| 捷運市政府站(臺灣大道) | `TAICHUNG_CITY_HALL_MRT` | 南下 | 9010 |
| 中清忠明路口 | `ZHONGQING_ZHONGMING` | 南下 | 1866 |
| 中清健行路口 | `ZHONGQING_JIANXING` | 南下 | 1866 |
| 科學博物館(臺灣大道) | `NATIONAL_MUSEUM_NATURAL_SCIENCE` | 南下 | 9010 |
| 莒光新城 | `JUGUANG_NEW_VILLAGE` | 南下 | 1866 |
| 五權學士路口 | `WUQUAN_XUESHI` | 南下 | 1866 |
| 臺中二中 | `TAICHUNG_SECOND_HS` | 南下 | 1866 |
| 中山代售處 | `ZHONGSHAN_AGENCY` | 北上 | 1866 |
| 臺中一中 | `TAICHUNG_FIRST_HS` | 南下 | 1866 |
| 民權路口 | `MINQUAN_INTERSECTION` | 南下 | 9010 |
| 臺中教育大學 | `TAICHUNG_EDUCATION_UNIVERSITY` | 南下 | 9010 |
| 臺中公園(雙十路) | `TAICHUNG_PARK_SHUANGSHI` | 南下 | 1866 |
| 國光客運臺中車站 | `TAICHUNG_KUOKUANG` | 雙向 | 1866 |
| 臺中州廳 | `TAICHUNG_PREFECTURAL_HALL` | 南下 | 9010 |
| 臺中車站(大智北路) | `TAICHUNG_STATION_DAZHI` | 北上 | 9010 |
| 臺中車站(民族路口) | `TAICHUNG_STATION_MINZU` | 南下 | 9010 |

## TDX 支線／業者／班表來源

| 支線 UID | Direction | 業者 ID | 原始筆數 | 已交付筆數 |
| --- | --- | --- | --- | --- |
| THB186601 | 0 | 45 | 7 | 7 |
| THB186602 | 1 | 45 | 5 | 0 |
| THB1866B1 | 0 | 45 | 17 | 17 |
| THB1866B2 | 1 | 45 | 15 | 15 |
| THB1866C2 | 1 | 45 | 1 | 1 |
| THB901001 | 0 | 13 | 17 | 17 |
| THB901001 | 0 | 56 | 45 | 45 |
| THB901002 | 1 | 13 | 15 | 15 |
| THB901002 | 1 | 56 | 47 | 47 |

## 本機驗證

- 35 項 Python 測試：中部線雙向、兩業者班表配對、部分時刻路段、沒有清大時刻的排除、起站時間語意、日期例外與跨午夜、缺路線／業者／核心班次拒收、來源身份驗證、GPS／抓取順序正規化及每次六個資料請求；亦保留既有同步與提醒檢查。
- 使用 App 現有實際 Kotlin 解析器與查詢引擎，14 路線、5 分頁、零警告；580 組日期、清大／新竹轉運站、台中目的地與雙向查詢通過。新竹轉運站自動分類正常，清大與轉運站可查各自官方上車時刻。
- 已確認 9010 大智北路／民族路口方向不同；每個列出的班次都有官方上下車站時刻，未使用到站估算。
- 驗證 1866 C2：10/26 日期例外排除，10/27 恢復；將未知分頁代號交給實際解析器時，其他 TRA/HSR/TAIPEI/SOUTH 分頁均保留。此為未知代號行為驗證，沒有啟動模擬器。
- 原有一項南部測試把「只有起站時間」fixture 誤當成完整班次；本機僅修正該測試資料的建構，沒有更動南部正式轉換邏輯，現有南部修正仍保留。

## 發布的檔案與資料更新方式

- scripts/sync_transit.py：加入 CENTRAL 白名單、站點映射與逐班轉換；原有 12 路線邏輯保持。
- tests/test_transit_central.py：新增中部測試；tests/test_transit_south.py：隔離舊功能測試並修正完整 fixture。
- docs/transit-central.md、docs/transit-sync.md：來源、站點代號、限制與使用說明。
- docs/v1/transit.json、docs/v1/manifest.json：由正式同步更新；只有實質異動改版本時間。
- 既有 workflow 無須改排程，仍台灣時間 05:30／17:30、每次六個白名單資料請求；沿用 TDX_CLIENT_ID／TDX_CLIENT_SECRET Secrets，App 不連 TDX。

來源：[TDX API](https://tdx.transportdata.tw/api-service/swagger)、[公路局 1866](https://www.taiwanbus.tw/eBUSPage/Query/QueryResult.aspx?rno=18660)、[公路局 9010](https://www.taiwanbus.tw/eBUSPage/Query/QueryResult.aspx?rno=90100)。詳細站序與時刻以本次 TDX 原始資料為準。
