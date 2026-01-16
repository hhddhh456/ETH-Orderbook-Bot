# -*- coding: utf-8 -*-
import asyncio # 非同步支援
import time # 時間函數
from datetime import datetime # 日期時間
import pandas as pd # 資料處理
import requests # HTTP 請求
from telegram import Bot #  Telegram 機器人
from collections import deque # 雙端佇列
import numpy as np # 數值計算

# ==========================================
# ▼▼▼ 正式參數設定區 (依據你的要求) ▼▼▼
# ==========================================
try:
    from config import TOKEN, CHAT_ID # 從 config.py 載入設定
except ImportError:
    print("錯誤：找不到 config.py！請先建立設定檔。")
    exit()
PAIR = "ETHUSDT"
DEPTH_LIMIT = 100 # 深度限制

# 1. 巨單設定
# 要求 5000.0，這是一個非常巨大的數字
BIG_QTY = 5000.0 # 巨單門檻            

# 2. OBI 設定
# 門檻 0.33，10 次需達標 7 次
OBI_ALERT = 0.33          
WINDOW_SIZE = 10          
WINDOW_REQUIRED = 7      

CHECK_INTERVAL = 10  # 每 10 秒檢查一次
COOLDOWN_SEC = 60 # 發送警報後冷卻 60 秒

# 3. 真空設定
# 比較過去 50 次歷史平均，低於 70% (0.7) 觸發
BIN_SIZE = 100 # 美金
N_BINS = 3 # 監控三個區間
VACUUM_THRESHOLD = 0.7 # 70%
VACUUM_DURATION = 1 # 秒
VACUUM_HISTORY_WINDOW = 50 # 歷史資料長度
# ==========================================

last_push_ts = 0.0
obi_window = deque(maxlen=WINDOW_SIZE) 
vacuum_start_time = None
vacuum_bin_history = {}

async def send_telegram_message(token: str, chat_id: str, text: str):
    try:
        async with Bot(token=token) as bot:
            await bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        print(f"TG 發送失敗: {e}")

# ==========================================
# ▲▼▲▼ 測試開關 (正式上線請設為 False) ▼▲▼▲
MOCK_TEST_MODE = False
# 設為 True 會強制連續模擬真空狀態
FORCE_VACUUM_TEST = False 
# ==========================================

# 全域計數器，用來製造數據落差
test_counter = 0

def fetch_orderbook_and_metrics():
    global test_counter
    # --- [上帝模式] 模擬測試區 ---
    if MOCK_TEST_MODE:
        import random
        test_counter += 1
        
        if FORCE_VACUUM_TEST:
            scenario = 'vacuum'
            print(f"[⚠️強制真空測試中 #{test_counter}]", end=" ")
        else:
            scenario = random.choice(['normal', 'pump', 'dump', 'whale', 'vacuum'])
            print("[⚠️隨機模擬]", end=" ")
        
        # 初始化
        fake_bids = pd.DataFrame(columns=["price", "quantity"]).astype(float)
        fake_asks = pd.DataFrame(columns=["price", "quantity"]).astype(float)
        empty_df = pd.DataFrame(columns=["price", "quantity"]).astype(float)
        obi = 0.0
        mid = 3300.0 
        
        if scenario == 'vacuum':
            # 前 10 次給 1000 顆，第 11 次崩跌
            if test_counter <= 10:
                fake_asks = pd.DataFrame([
                    [3310.0, 1000.0], [3410.0, 1000.0], [3510.0, 1000.0]
                ], columns=["price", "quantity"])
                obi = 0.0 
            else:
                fake_asks = pd.DataFrame([
                    [3310.0, 1.0], [3410.0, 1.0], [3510.0, 1.0]
                ], columns=["price", "quantity"])
                obi = -0.5
            return obi, empty_df, empty_df, fake_bids, fake_asks, mid
        
        elif scenario == 'whale':
             fake_bids = pd.DataFrame([[3200.0, 10000.0]], columns=["price", "quantity"])
             obi = 0.5
             return obi, fake_bids, empty_df, fake_bids, fake_asks, mid
        
        return obi, empty_df, empty_df, fake_bids, fake_asks, mid

    # --- [正常模式] ---
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/depth",
            params={"symbol": PAIR, "limit": DEPTH_LIMIT},
            timeout=10
        )
        r.raise_for_status()
        results = r.json()
        bids = pd.DataFrame(results["bids"], columns=["price", "quantity"]).astype(float)
        asks = pd.DataFrame(results["asks"], columns=["price", "quantity"]).astype(float)
        
        buy_sum = bids["quantity"].sum()
        sell_sum = asks["quantity"].sum()
        obi = (buy_sum - sell_sum) / (buy_sum + sell_sum) if buy_sum + sell_sum > 0 else 0.0
        
        big_bid = bids[bids["quantity"] > BIG_QTY]
        big_ask = asks[asks["quantity"] > BIG_QTY]
        
        best_bid = bids["price"].max() if not bids.empty else float("nan")
        best_ask = asks["price"].min() if not asks.empty else float("nan")
        mid = (best_bid + best_ask) / 2.0 if pd.notna(best_bid) and pd.notna(best_ask) else float("nan")
        
        return obi, big_bid, big_ask, bids, asks, mid
    except Exception as e:
        print(f"API Error: {e}")
        return 0.0, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 0.0

def describe_obi(obi: float) -> str:
    # 這是你指定的文字邏輯
    if obi >= 0.33:
        return "強勢買壓（買方主導）"
    elif 0.2 <= obi < 0.33:
        return "買方佔優（偏多）"
    elif -0.2 < obi < 0.2:
        return "中性（多空均衡）"
    elif -0.33 < obi <= -0.2:
        return "賣方佔優（偏空）"
    else:
        return "強勢賣壓（賣方主導）"

def build_alert(obi, obi_desc, mid, big_bid, big_ask, vacuum_warn=""):
    # --- 動態標題邏輯 ---
    if not big_bid.empty or not big_ask.empty:
        title_tag = "🐋發現巨鯨"
    elif vacuum_warn:
        title_tag = "⚠️流動性真空"
    else:
        title_tag = obi_desc.split("（")[0] if "（" in obi_desc else obi_desc
        title_tag = f"🔥{title_tag}"

    lines = [
        f"【{title_tag}】{PAIR}",      
        f"現價: {mid:.2f}",
        f"OBI: {obi:.3f}",
        f"詳細: {obi_desc}",
    ]
    
    if not big_ask.empty:
        lines.append(f"🔴 巨量賣單: {len(big_ask)}筆 (Max: {big_ask['quantity'].max():.1f})")
    if not big_bid.empty:
        lines.append(f"🟢 巨量買單: {len(big_bid)}筆 (Max: {big_bid['quantity'].max():.1f})")
    if vacuum_warn:
        lines.append(f"⚠️ 真空警報: {vacuum_warn}")
        
    return "\n".join(lines)

def calc_liquidity_bins(order_book_df, price_now, bin_size, n_bins, side='ask'):
    bins = []
    if order_book_df.empty: return []
    
    for i in range(n_bins):
        if side == 'ask':
            low = price_now + i * bin_size
            high = price_now + (i+1) * bin_size
            mask = (order_book_df['price'] >= low) & (order_book_df['price'] < high)
            label_text = f"{low:.0f}-{high:.0f}"
        else: # bid
            high = price_now - i * bin_size
            low = price_now - (i+1) * bin_size
            mask = (order_book_df['price'] <= high) & (order_book_df['price'] > low)
            label_text = f"{low:.0f}-{high:.0f}"
            
        total_in_bin = order_book_df[mask]['quantity'].sum()
        bins.append((label_text, total_in_bin))
    return bins

def vacuum_monitor(order_book_df, price_now, side='ask'):
    global vacuum_bin_history, vacuum_start_time
    if order_book_df.empty: return False, ""
    
    bins = calc_liquidity_bins(order_book_df, price_now, BIN_SIZE, N_BINS, side)
    warn_zones = []
    all_gaps_low = True
    now_ts = time.time()
    
    for idx, (label_text, qty) in enumerate(bins):
        hkey = (side, idx)
        if hkey not in vacuum_bin_history:
            vacuum_bin_history[hkey] = deque(maxlen=VACUUM_HISTORY_WINDOW)
        
        vacuum_bin_history[hkey].append(qty)
        
        if len(vacuum_bin_history[hkey]) > 3:
            avg_q = np.mean(vacuum_bin_history[hkey])
            if avg_q > 0 and qty < avg_q * VACUUM_THRESHOLD:
                warn_zones.append(f"{label_text}({qty:.1f}/{avg_q:.1f})")
            else:
                all_gaps_low = False
        else:
            all_gaps_low = False

    vacuum = False
    warn_msg = ""
    
    if all_gaps_low and len(warn_zones) == N_BINS:
        if vacuum_start_time is None:
            vacuum_start_time = now_ts
        elif now_ts - vacuum_start_time >= VACUUM_DURATION:
            vacuum = True
            warn_msg = f"連續{VACUUM_DURATION}秒量縮: " + ", ".join(warn_zones)
    else:
        vacuum_start_time = None
        
    return vacuum, warn_msg

async def loop_runner():
    global last_push_ts
    print(f"🚀 正式監控啟動 - {PAIR}")
    print(f"設定: OBI>{OBI_ALERT}({WINDOW_REQUIRED}/{WINDOW_SIZE}), 巨單>{BIG_QTY}, 真空<{VACUUM_THRESHOLD*100}%")
    print("-" * 50) 

    while True:
        try:
            # 1. 獲取數據
            obi, big_bid, big_ask, bids, asks, mid = fetch_orderbook_and_metrics()
            
            # 2. 邏輯計算
            obi_window.append(obi)
            extreme_times = sum(abs(x) >= OBI_ALERT for x in obi_window)
            is_obi_trigger = (len(obi_window) == WINDOW_SIZE and extreme_times >= WINDOW_REQUIRED)
            has_whale = (not big_bid.empty) or (not big_ask.empty)
            vacuum, vacuum_warn = vacuum_monitor(asks, mid, side='ask')

            # 3. 螢幕顯示區
            now_str = datetime.now().strftime('%H:%M:%S')
            obi_desc = describe_obi(obi)
            simple_desc = obi_desc.split("（")[0] if "（" in obi_desc else obi_desc
            console_msg = f"[{now_str}] OBI:{obi:.3f} | {simple_desc}"
            
            if has_whale: console_msg += " [🐋巨單]"
            if is_obi_trigger: console_msg += " [🔥達標]"
            if vacuum: console_msg += " [⚠️真空]"
            print(console_msg, flush=True)

            # 4. Telegram 發送判斷
            is_neutral = "中性" in obi_desc
            
            if (is_obi_trigger and not is_neutral) or has_whale or vacuum:
                will_push = True
            else:
                will_push = False
            
            now = time.time()
            if will_push:
                if now - last_push_ts >= COOLDOWN_SEC:
                    print("   >>> 🚀 發送 Telegram 警報...", flush=True)
                    msg = build_alert(obi, obi_desc, mid, big_bid, big_ask, vacuum_warn if vacuum else "")
                    await send_telegram_message(TOKEN, CHAT_ID, msg)
                    last_push_ts = now

        except Exception as e:
            print(f"❌ 發生錯誤: {e}", flush=True)
            
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(loop_runner())
    except KeyboardInterrupt:
        print("停止監控")
