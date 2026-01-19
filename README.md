ETHUSDT Order Book Bot

1. System Overview  
Built on Python AsyncIO architecture.  
Core Features  
- OBI Pressure Monitoring (Order Book Imbalance):  
  Calculates the ratio of total buy and sell orders.  
  Purpose: Determines whether the market is currently "buy-dominated" or "sell-dominated", serving as a leading indicator for short-term price breakouts.  
- Liquidity Vacuum Detection:  
  Monitors whether order volume in specific price ranges is significantly below historical averages.  
  Purpose: When orders are thin, even small market orders can cause severe slippage.  
- Whale Watch:  
  Detects abnormal orders exceeding the set threshold (5000 ETH).  
  Purpose: Identifies large players' intentions to support (Buy Wall) or suppress (Sell Wall) the price.  
- Smart Alert:  
  Features dynamic priority-based notification titles to ensure the most critical information is seen at a glance on mobile devices.  
________________________________________

2. System Architecture  
The program adopts a lightweight ETL (Extract-Transform-Load) architecture with sliding window signal filtering.  

A. Data Ingestion Layer  
Source: Binance Spot API (/api/v3/depth).  
Frequency: Every 10 seconds (controlled by CHECK_INTERVAL).  
Depth: Limited to the top 100 levels on both sides (DEPTH_LIMIT = 100), focusing on frontline orders.  

B. Data Processing Layer – Algorithm Core  
This is the "brain" of the system, consisting of three mathematical models:  

1. OBI Model (Order Book Imbalance)  
   Formula: \mathrm{OBI} = \frac{Total Buy Volume - Total Sell Volume}{Total Buy Volume + Total Sell Volume}  
   Range: -1 (extremely bearish) to +1 (extremely bullish).  
   Filtering: Uses a FIFO queue of length 10 (obi_window).  
   Trigger Logic: Requires at least 7 out of the last 10 samples to exceed the threshold of 0.33 for a valid trend. This effectively eliminates flickering noise from fleeting orders.  

2. Vacuum Model  
   Logic: Divides price ranges above/below the current price into 3 bins, each 100 USDT wide.  
   Comparison: Against the moving average of the past 50 samples (VACUUM_HISTORY_WINDOW).  
   Trigger Condition: Current volume below 70% of historical average (VACUUM_THRESHOLD = 0.7) in all 3 bins simultaneously.  

3. Whale Model  
   Logic: Scans the top 100 levels for orders with quantity > 5000.0.  

C. Decision & Alerting Layer  
Security: Token loaded from config.py for separation of code and secrets.  
Dynamic Priority Titles:  
Highest: 【 Whale Detected】  
Secondary: 【Liquidity Vacuum】  
Trend: 【Strong Buy/Sell Pressure】  
Neutral Filtering: System auto-mutes in neutral conditions without special events to avoid noise.  
Cooldown: 60-second mandatory cooldown after each alert (COOLDOWN_SEC).  

________________________________________

3. Data Source Deep Dive  
The system relies entirely on Binance Spot public market data:  

1. Data Provider  
Name: Binance Spot API  

2. Payload Content  
Each request retrieves an ETH/USDT order book snapshot containing:  
Bids (buy orders): Sorted high to low. Example: [3300.50, 10.5] (bid 10.5 ETH at 3300.50).  
Asks (sell orders): Sorted low to high. Example: [3300.51, 5.0] (ask 5.0 ETH at 3300.51).  

3. Data Processing Flow  
Raw Data: JSON format.  
Cleaning: Converted to pandas.DataFrame with float types.  
Feature Engineering: Sum volumes to derive OBI and filter whale orders.  

________________________________________

4. Configuration Guide  
Current parameters are tuned for "extreme event capture mode", filtering out 99% of normal fluctuations to alert only on significant events.  

Parameter | Value | Description | Adjustment Impact  
--- | --- | --- | ---  
PAIR | "ETHUSDT" | Monitored pair | Change to "BTCUSDT" etc.  
BIG_QTY | 5000.0 | Whale threshold | 5000 ETH (~$15M) – nuclear-level, rarely triggered, ensures only super-whales.  
OBI_ALERT | 0.33 | Pressure threshold | Represents ~2:1 imbalance.  
WINDOW_SIZE | 10 | Observation window | Past 10 samples (~100 seconds).  
WINDOW_REQUIRED | 7 | Required hits | 70% consistency to trigger, greatly reduces false positives.  
VACUUM_THRESHOLD | 0.7 | Vacuum coefficient | Below 70% of historical average. Increase to 0.8-0.9 for higher sensitivity.  
VACUUM_HISTORY | 50 | History length | References past 50 samples (~500 seconds) average liquidity.
