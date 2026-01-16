ETHUSDT Order Book Bot

1. 系統簡介 (System Overview)
一套基於 Python AsyncIO 架構開發的 即時市場微結構 (Market Microstructure) 監控機器人。監控 Order Book的即時狀態，捕捉 ETHUSDT 的訂單簿失衡與流動性異常。
核心功能
OBI 壓力監測 (Order Book Imbalance)：
計算買賣雙方的掛單總量比例。
用途：判斷市場當下是「買方主導」還是「賣方主導」，作為價格短線爆發的領先指標。
流動性真空偵測 (Liquidity Vacuum)：
監控特定價格區間的掛單量是否顯著低於歷史平均。
用途：當掛單稀薄時，少量的市價單即可造成價格劇烈滑價 (Slippage)。
巨單監控 (Whale Watch)：
偵測單筆掛單數量超過設定值 (5000 ETH) 的異常訂單。
用途：識別主力機構的護盤 (Buy Wall) 或壓盤 (Sell Wall) 意圖。
Smart Alert：
具備「優先級排序」的動態標題通知，確保手機第一眼看到最重要的資訊（如巨單 > 真空 > 一般趨勢）。
________________________________________
2. 系統架構解析 (System Architecture)
程式採用 ETL (Extract-Transform-Load) 微縮架構，並配合 滑動窗口 (Sliding Window) 進行訊號濾波。
A. 數據擷取層 (Data Ingestion)
來源：Binance Spot API (/api/v3/depth)。
頻率：每 10 秒一次 (由 CHECK_INTERVAL 控制)。
深度：由 DEPTH_LIMIT = 100 控制，鎖定買賣雙方最前線的 100 檔掛單。
B. 數據處理層 (Data Processing) - 演算法核心
這是程式的「大腦」，由三個數學模型組成：
1. OBI 模型 (Order Book Imbalance)
公式：\mathrm{OBI}=總買量-總賣量總買量+總賣量
區間：-1 (極度看空) 到 +1 (極度看多)。
過濾機制：採用長度為 10 的 FIFO 佇列 (obi_window)。
觸發邏輯：需在最近 10 次採樣中，有 7 次 超過閾值 0.33，才認定為有效趨勢。此設計有效消除了掛單閃爍 (Flickering) 的雜訊。
2. 真空模型 (Vacuum Model)
邏輯：將現價上方/下方劃分為 3 個 價格區間 (Bin)，每個區間寬度 100 USDT。
比較基準：與該區間過去 50 次 (VACUUM_HISTORY_WINDOW) 的歷史移動平均量做比較。
觸發條件：當前掛單量低於歷史均值的 70% (VACUUM_THRESHOLD = 0.7)，且 3 個區間同時 發生此狀況。
3. 巨單模型 (Whale Model)
邏輯：直接掃描前 100 檔掛單，篩選出 quantity > 5000.0 的超級大單。
C. 決策與發送層 (Decision & Alerting)
資安分離：透過 config.py 讀取 Token，實現程式碼與機密資料分離。
動態標題 (Dynamic Priority)：
最高優先：【🐋發現巨鯨】
次要優先：【⚠️流動性真空】
一般趨勢：【🔥強勢買壓/賣壓】
中性過濾：若市場處於「中性 (Neutral)」狀態且無特殊事件，系統將自動靜音，避免無效干擾。
冷卻機制：發送警報後強制冷卻 60 秒 (COOLDOWN_SEC)。
________________________________________
3. 數據源與獲取機制詳解 (Data Source Deep Dive)
本系統運作完全依賴於 Binance (幣安) 現貨公開市場數據，細節如下：
1. 數據供應商
名稱：Binance Spot API
2. 獲取內容 (Payload)
系統每次請求獲取 ETH/USDT 的訂單簿快照，包含核心陣列：
Bids (買單陣列)：價格由高到低排序。例：[3300.50, 10.5] (在 3300.50 想買 10.5 顆)。
Asks (賣單陣列)：價格由低到高排序。例：[3300.51, 5.0] (在 3300.51 想賣 5.0 顆)。
3. 數據處理流程
原始數據：接收 JSON 格式數據。
清洗轉換：使用 pandas.DataFrame 將字串轉為浮點數 (float)。
特徵工程：計算總量 sum() 導出 OBI，並進行巨單篩選。
________________________________________
4. 參數設定與調整指南 (Configuration Guide)
本版本參數已調整為 「極端行情捕捉模式」，旨在過濾掉 99% 的日常波動，僅針對重大事件發報。
參數名稱	設定值	功能描述	調整影響
PAIR	"ETHUSDT"	監控幣種	可改為 "BTCUSDT" 等。
BIG_QTY	5000.0	巨單門檻	5000 ETH (約 1500 萬美金) 是核彈級設定，極難觸發，確保只抓超級主力。
OBI_ALERT	0.33	壓力閾值	代表多空力量差距達 2 倍以上。
WINDOW_SIZE	10	觀察窗口	觀察過去 10 次 (約 100 秒) 的數據。
WINDOW_REQUIRED	7	達標次數	需 70% 時間維持異常才發報，大幅降低誤報率。
VACUUM_THRESHOLD	0.7	真空係數	低於歷史均值 70% 即觸發。若需更敏感可調至 0.8 或 0.9。
VACUUM_HISTORY	50	歷史長度	參考過去 50 次採樣 (約 500 秒) 的平均流動性。
