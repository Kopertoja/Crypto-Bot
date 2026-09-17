import os
import time
import csv
from datetime import datetime, timedelta
import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
import ccxt
import pandas as pd
import numpy as np
import requests
import json
import sqlite3
import matplotlib.pyplot as plt
import threading
import asyncio
import websockets
from collections import deque
from groq import Groq

# --- IMPORTY HYPERLIQUID ---
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# ==========================================
# KONFIGURACJA POCZĄTKOWA
# ==========================================
load_dotenv()
WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
HL_PRIVATE_KEY = os.getenv('HL_WALLET_PRIVATE_KEY')

if not HL_PRIVATE_KEY:
    print("❌ BŁĄD: Brak klucza HL_WALLET_PRIVATE_KEY w pliku .env!")
    exit()

# ==========================================
# ⚙️ ZASADY ZARZĄDZANIA POZYCJĄ (PITBULL) 
# ==========================================
SL_PROCENT = 0.030          
BREAKEVEN_PROCENT = 0.020   
TRAILING_PROCENT = 0.015    

# ⚙️ TUTAJ ZMIENIASZ MONETĘ (ETH lub BTC)
COIN_SYMBOL = 'ETH'
DZWIGNIA = 10 # Sztywna dźwignia

# ==========================================
# 1. BAZA DANYCH I RAPORTY
# ==========================================
def setup_db():
    conn = sqlite3.connect(f'trades_history_{COIN_SYMBOL.lower()}_hl.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  symbol TEXT, side TEXT, entry_price REAL, 
                  exit_price REAL, pnl REAL, date TEXT)''')
    conn.commit()
    return conn

db_conn = setup_db()

def zapisz_trade_do_bazy(symbol, side, entry_price, exit_price, pnl):
    try:
        c = db_conn.cursor()
        data = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO trades (symbol, side, entry_price, exit_price, pnl, date) VALUES (?, ?, ?, ?, ?, ?)",
                  (symbol, side, entry_price, exit_price, pnl, data))
        db_conn.commit()
    except Exception as e:
        log_print(f"❌ Błąd zapisu do bazy: {e}")

def generuj_i_wyslij_raport_tygodniowy():
    try:
        df_db = pd.read_sql_query("SELECT * FROM trades", db_conn)
        if df_db.empty: return
        df_db['date'] = pd.to_datetime(df_db['date'])
        tydzien_temu = datetime.now() - timedelta(days=7)
        df_tydzien = df_db[df_db['date'] >= tydzien_temu]
        if df_tydzien.empty: return

        win_rate = (len(df_tydzien[df_tydzien['pnl'] > 0]) / len(df_tydzien)) * 100
        total_pnl = df_tydzien['pnl'].sum()
        
        plt.figure(figsize=(10, 5))
        df_tydzien['cumulative_pnl'] = df_tydzien['pnl'].cumsum()
        plt.plot(df_tydzien['date'], df_tydzien['cumulative_pnl'], marker='o', linestyle='-', color='g')
        plt.title(f'Tygodniowy PnL {COIN_SYMBOL} (HL) ({total_pnl:+.2f} USDC)')
        plt.xlabel('Data')
        plt.ylabel('Skumulowany Zysk (USDC)')
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(f'raport_tygodniowy_{COIN_SYMBOL.lower()}.png')
        plt.close()

        wiadomosc = (f"📈 **RAPORT TYGODNIOWY {COIN_SYMBOL} HL** 📈\n"
                     f"Liczba trade'ów: {len(df_tydzien)}\n"
                     f"Skuteczność: **{win_rate:.1f}%**\n"
                     f"Zysk Netto: **{total_pnl:+.2f} USDC**")
        
        with open(f'raport_tygodniowy_{COIN_SYMBOL.lower()}.png', 'rb') as f:
            requests.post(WEBHOOK_URL, data={'payload_json': json.dumps({"content": wiadomosc})}, files={'file': f})
    except Exception as e:
        log_print(f"❌ Błąd przy generowaniu raportu: {e}")

# ==========================================
# MODUŁ ML - ZBIERANIE DANYCH 
# ==========================================
ML_FILE = f'ml_dataset_{COIN_SYMBOL.lower()}_hl.csv'

def inicjalizuj_plik_ml():
    if not os.path.exists(ML_FILE):
        with open(ML_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Data', 'Symbol', 'Typ', 'Cena_Wejscia', 'RSI_15m', 'CVD_5m', 'Trend_4H_Binary', 'OB_Ratio', 'PnL', 'Sukces'])

inicjalizuj_plik_ml()

def zapisz_trade_do_ml(snapshot, pnl):
    if not snapshot: return 
    try:
        sukces = 1 if pnl > 0 else 0
        with open(ML_FILE, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                snapshot.get('symbol', 'Brak'), snapshot.get('typ', 'Brak'), snapshot.get('cena', 0),
                snapshot.get('rsi', 0), snapshot.get('cvd', 0), snapshot.get('trend_4h', 0),
                snapshot.get('ob_ratio', 1), round(pnl, 4), sukces
            ])
        log_print(f"🧠 [ML Dataset] Zapisano próbkę danych. Wynik: {sukces}")
    except Exception as e:
        log_print(f"❌ [ML Dataset] Błąd zapisu: {e}")

# ==========================================
# 2. DISCORD & LOGI 
# ==========================================
def wyslij_discord(wiadomosc):
    if not WEBHOOK_URL: return
    try: requests.post(WEBHOOK_URL, json={"content": wiadomosc}, timeout=5)
    except: pass

logger = logging.getLogger(f"crypto_bot_hl_{COIN_SYMBOL.lower()}")
logger.setLevel(logging.INFO)
if not logger.handlers:
    file_handler = TimedRotatingFileHandler(f'bot_hl_{COIN_SYMBOL.lower()}_log.txt', when='midnight', interval=1, backupCount=7, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(file_handler)

def log_print(message):
    print(message, flush=True); logger.info(message)

# ==========================================
# CZARNA SKRZYNKA (RECOVERY MODULE)
# ==========================================
STATE_FILE = f'stan_bota_{COIN_SYMBOL.lower()}_hl.json'
current_ml_snapshot = {}

def zapisz_stan_bota(typ, wejscie, sl, max_cena, min_cena, czas, ml_snap):
    stan = {
        'typ': typ, 'wejscie': wejscie, 'sl': sl, 
        'max_cena': max_cena, 'min_cena': min_cena, 
        'czas': czas, 'ml_snapshot': ml_snap
    }
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(stan, f)
    except Exception as e: 
        log_print(f"⚠️ Błąd zapisu Czarnej Skrzynki: {e}")

def usun_stan_bota():
    if os.path.exists(STATE_FILE):
        try: os.remove(STATE_FILE)
        except: pass

# ==========================================
# MODUŁ WEBSOCKET: ORDER FLOW (CVD Z BINANCE DLA PRECYZJI)
# ==========================================
live_trades_buffer = deque(maxlen=10000)

def pobierz_aktualne_cvd():
    now_ms = time.time() * 1000
    piec_min_temu = now_ms - (5 * 60 * 1000)
    ostatnie = [t for t in live_trades_buffer if t['time'] >= piec_min_temu]
    if not ostatnie: return 0.0
    return round(sum(t['delta'] for t in ostatnie), 2)

async def _ws_worker(symbol_str):
    url = f"wss://stream.binancefuture.com/ws/{symbol_str}@aggTrade"
    while True:
        try:
            async with websockets.connect(url) as ws:
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    wolumen = float(data['q'])
                    is_sell = data['m']
                    delta = -wolumen if is_sell else wolumen
                    live_trades_buffer.append({'time': data['T'], 'delta': delta})
        except Exception as e:
            await asyncio.sleep(5)

def start_orderflow_listener(symbol_str):
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_ws_worker(symbol_str))
    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

# ==========================================
# 3. ZAAWANSOWANE ZBIERANIE DANYCH (AI GROQ)
# ==========================================
client = Groq(api_key=GROQ_API_KEY)

def pobierz_kontekst_24h(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        high_24h = float(ticker['high'])
        low_24h = float(ticker['low'])
        current_price = float(ticker['last'])
        volatility_pct = ((high_24h - low_24h) / low_24h) * 100
        position_in_range = (current_price - low_24h) / (high_24h - low_24h) if high_24h > low_24h else 0.5
        return volatility_pct, position_in_range, high_24h, low_24h
    except Exception as e: return 0.0, 0.5, 0.0, 0.0

def pobierz_weryfikacje_5m(exchange, symbol):
    try:
        ohlcv_5m = exchange.fetch_ohlcv(symbol, '5m', limit=10)
        df_5m = pd.DataFrame(ohlcv_5m, columns=['Timestamp', 'O', 'H', 'L', 'C', 'V'])
        ost_wolumen = df_5m['V'].iloc[-2]
        sredni_wolumen = df_5m['V'].iloc[:-2].mean()
        zmiana_ceny = ((df_5m['C'].iloc[-2] - df_5m['O'].iloc[-2]) / df_5m['O'].iloc[-2]) * 100
        
        if ost_wolumen > (sredni_wolumen * 1.5) and zmiana_ceny > 0.1:
            return f"🟢 SILNY POPYT 5m (Wolumen x{ost_wolumen/sredni_wolumen:.1f})"
        elif ost_wolumen > (sredni_wolumen * 1.5) and zmiana_ceny < -0.1:
            return f"🔴 SILNA PODAŻ 5m (Wolumen x{ost_wolumen/sredni_wolumen:.1f})"
        else:
            return "🟡 Brak wyraźnego dowodu z ulicy"
    except Exception as e: return "Błąd weryfikacji 5m"

def pobierz_zaawansowane_dane(exchange, symbol):
    dane_makro = {}
    try:
        ohlcv_8h = exchange.fetch_ohlcv(symbol, '1h', limit=8)
        df_8h = pd.DataFrame(ohlcv_8h, columns=['Timestamp', 'O', 'H', 'L', 'C', 'V'])
        zmiana_8h = ((df_8h['C'].iloc[-1] - df_8h['O'].iloc[0]) / df_8h['O'].iloc[0]) * 100
        dane_makro['dynamika_8h'] = f"{zmiana_8h:+.2f}%"

        ohlcv_4h = exchange.fetch_ohlcv(symbol, '4h', limit=100)
        df_4h = pd.DataFrame(ohlcv_4h, columns=['Timestamp', 'O', 'H', 'L', 'C', 'V'])
        ema_200 = df_4h['C'].ewm(span=200, adjust=False).mean().iloc[-1]
        cena_4h = df_4h['C'].iloc[-1]
        dane_makro['trend_4h'] = "HOSSA" if cena_4h > ema_200 else "BESSA"
        dane_makro['ml_trend'] = 1 if cena_4h > ema_200 else 0 

        ob = exchange.fetch_order_book(symbol, limit=50)
        bids_volume = sum([bid[1] for bid in ob['bids']])
        asks_volume = sum([ask[1] for ask in ob['asks']])
        dane_makro['ob_imbalance'] = f"Popyt {bids_volume:.1f} vs Podaż {asks_volume:.1f}"
        dane_makro['ml_ob_ratio'] = round(bids_volume / asks_volume, 2) if asks_volume > 0 else 1.0 
        dane_makro['potwierdzenie_5m'] = pobierz_weryfikacje_5m(exchange, symbol)
    except Exception as e:
        dane_makro['trend_4h'] = "Nieznany"; dane_makro['dynamika_8h'] = "Brak"; dane_makro['ob_imbalance'] = "Brak"
        dane_makro['ml_trend'] = 0; dane_makro['ml_ob_ratio'] = 1.0
    return dane_makro

def skonsultuj_z_ai(symbol, typ_sygnalu, current_price, df_kontekst, makro_dane, context_24h):
    log_print(" 🧠 Analiza DUAL-MODE (Groq AI). Wysyłam...")
    cvd_5m_live = pobierz_aktualne_cvd()
    vol_24h, pos_24h, high_24h, low_24h = context_24h
    faza_rynku = "Szczyt" if pos_24h > 0.8 else ("Dołek" if pos_24h < 0.2 else "Środek")
    
    prompt = f"""
    You are an elite, cold-blooded cryptocurrency trading AI. Your ONLY goal is to maximize ROI and protect capital. 
    Evaluate this {typ_sygnalu} signal at price {current_price} for {symbol}. 
    Make a ruthless, data-driven decision. Do NOT accept mediocre setups.

    [MARKET CONTEXT]
    - Phase: {faza_rynku}
    - 8H Momentum: {makro_dane['dynamika_8h']}
    - 4H Trend: {makro_dane['trend_4h']}
    
    [LIVE DATA]
    - Order Book Imbalance: {makro_dane['ob_imbalance']}
    - 5m Volume Confirmation: {makro_dane['potwierdzenie_5m']}
    - Live CVD (5m): {cvd_5m_live}

    [DECISION MATRIX]
    1. CAPITAL PROTECTION (AUTO-REJECT): If Order Book shows clear dominance against our position AND 5m volume/CVD is dead or contradictory, output "NIE".
    2. SPOOFING DETECTOR (AUTO-REJECT): If there is a huge Order Book wall but CVD and 5m volume are weak, it's a trap. Output "NIE".
    3. TREND ALIGNMENT (APPROVE): If the signal aligns with the macro trend (8H/4H), and Order Book + Volume support the continuation, output "TAK".
    4. MEAN REVERSION (STRICT APPROVE): If trading against the macro trend (catching a top/bottom), output "TAK" ONLY IF there is a clear, confirmed reversal (e.g., Order Book shift in our favor PLUS strong 5m volume/CVD confirmation). Otherwise, reject it.

    Return ONLY a valid JSON object without any additional text:
    {{"decyzja": "TAK" or "NIE", "powod": "Krótki, analityczny powód po polsku (max 15 słów)"}}
    """
    try:
        res = client.chat.completions.create(
            messages=[{"role": "system", "content": "Zwracaj tylko poprawny JSON."},
                      {"role": "user", "content": prompt}],
            model="openai/gpt-oss-120b", temperature=0.1, response_format={"type": "json_object"}
        )
        wynik = json.loads(res.choices[0].message.content)
        
        # OTO NAPRAWIONA LINIJKA (podkreślnik + ładna emotka):
        log_print(f"🤖 [AI ODPOWIEDŹ]: Decyzja: {wynik.get('decyzja')} | Powód: {wynik.get('powod')}")
        
        return wynik.get('decyzja') == "TAK", wynik.get('powod', 'Brak powodu')
    except Exception as e:
        # Dodajemy logowanie błędu, żeby na przyszłość nic się nie chowało!
        log_print(f"❌ Błąd komunikacji z AI: {e}")
        return False, f"Błąd AI: {e}"

# ==========================================
# 4. INICJALIZACJA HYPERLIQUID 
# ==========================================
exchange = ccxt.hyperliquid({'enableRateLimit': True}) 
symbol_ccxt = f'{COIN_SYMBOL}/USDC:USDC' 
hl_coin = COIN_SYMBOL

hl_account = Account.from_key(HL_PRIVATE_KEY)
hl_info = Info(constants.MAINNET_API_URL, skip_ws=True)
hl_exchange = Exchange(hl_account, constants.MAINNET_API_URL)
wallet_address = hl_account.address.lower()

timeframe = '15m'
WINDOW = 20
MULTIPLIER = 1.3  
VOL_MULTIPLIER = 1.2

log_print(f"🚀 BOT V6 (HYPERLIQUID) dla {hl_coin} URUCHOMIONO!")
log_print(f"🔌 Portfel: {wallet_address}")

active_long = active_short = None
active_position_type = virtual_sl = entry_price = None
last_traded_candle_time = najwyzsza_cena_w_pozycji = najnizsza_cena_w_pozycji = None
ostatni_raport_tydzien = -1

# Uruchomienie Orderflow dla odpowiedniej monety
ws_symbol = "ethusdt" if COIN_SYMBOL == "ETH" else "btcusdt"
start_orderflow_listener(ws_symbol)
time.sleep(2)

# --- INICJALIZACJA CZARNEJ SKRZYNKI ---
wczytany_stan = None
if os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE, 'r') as f:
            wczytany_stan = json.load(f)
    except: pass

user_state = hl_info.user_state(wallet_address)
positions_data = user_state.get("assetPositions", [])
pos_amt = 0.0
for p in positions_data:
    if p.get("position", {}).get("coin") == hl_coin:
        pos_amt = float(p.get("position", {}).get("szi", 0.0))

if pos_amt != 0.0:
    if wczytany_stan and wczytany_stan.get('typ'):
        log_print(f"♻️ [RECOVERY] Wznawiam {wczytany_stan['typ']}. SL: {wczytany_stan['sl']}")
        active_position_type = wczytany_stan['typ']
        entry_price = wczytany_stan['wejscie']
        virtual_sl = wczytany_stan['sl']
        najwyzsza_cena_w_pozycji = wczytany_stan['max_cena']
        najnizsza_cena_w_pozycji = wczytany_stan['min_cena']
        last_traded_candle_time = wczytany_stan['czas']
        current_ml_snapshot = wczytany_stan.get('ml_snapshot', {})
    else:
        log_print("⚠️ [RECOVERY] Obca pozycja. Kamuflaż.")
        awaryjna_cena = float(exchange.fetch_ticker(symbol_ccxt)['last'])
        active_position_type = 'LONG' if pos_amt > 0 else 'SHORT'
        entry_price = awaryjna_cena
        virtual_sl = awaryjna_cena * (1 - SL_PROCENT) if pos_amt > 0 else awaryjna_cena * (1 + SL_PROCENT)
        najwyzsza_cena_w_pozycji = najnizsza_cena_w_pozycji = awaryjna_cena
        current_ml_snapshot = {}
        zapisz_stan_bota(active_position_type, entry_price, virtual_sl, najwyzsza_cena_w_pozycji, najnizsza_cena_w_pozycji, last_traded_candle_time, current_ml_snapshot)
else:
    usun_stan_bota()

# ==========================================
# GŁÓWNA PĘTLA BOTA
# ==========================================
while True:
    try:
        now = datetime.now()
        if now.weekday() == 6 and now.hour == 20 and now.isocalendar()[1] != ostatni_raport_tydzien:
            generuj_i_wyslij_raport_tygodniowy()
            ostatni_raport_tydzien = now.isocalendar()[1]

        ohlcv = exchange.fetch_ohlcv(symbol_ccxt, timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['Time'] = pd.to_datetime(df['Timestamp'], unit='ms').dt.strftime('%H:%M')
        
        delta = df['Close'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        df['RSI'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / down.ewm(com=13, adjust=False).mean())))
        
        df['Candle_Length'] = df['High'] - df['Low']
        df['Avg_Length'] = df['Candle_Length'].shift(1).rolling(WINDOW).mean()
        df['Avg_Volume'] = df['Volume'].shift(1).rolling(WINDOW).mean()
        
        df['Is_Signal_Long'] = (df['Candle_Length'] > (df['Avg_Length'] * MULTIPLIER)) & (df['Volume'] > (df['Avg_Volume'] * VOL_MULTIPLIER)) & (df['RSI'] < 60) 
        df['Is_Signal_Short'] = (df['Candle_Length'] > (df['Avg_Length'] * MULTIPLIER)) & (df['Volume'] > (df['Avg_Volume'] * VOL_MULTIPLIER)) & (df['RSI'] > 40)
                                 
        df['Entry_Long'] = np.where(df['Is_Signal_Long'], df['High'], np.nan)
        df['Entry_Short'] = np.where(df['Is_Signal_Short'], df['Low'], np.nan)
        
        last_closed_candle, current_candle = df.iloc[-2], df.iloc[-1]
        current_price = current_candle['Close']

        # --- ZARZĄDZANIE AKTYWNĄ POZYCJĄ ---
        if active_position_type:
            user_state = hl_info.user_state(wallet_address)
            positions_data = user_state.get("assetPositions", [])
            position_amt = 0.0
            for p in positions_data:
                if p.get("position", {}).get("coin") == hl_coin:
                    position_amt = float(p.get("position", {}).get("szi", 0.0))
            
            if position_amt == 0.0:
                log_print("ℹ️ Pozycja zamknięta z zewnątrz.")
                usun_stan_bota()
                active_position_type = active_long = active_short = None
            else:
                amt_abs = abs(position_amt)
                zmieniono_stan = False
                
                if active_position_type == 'LONG':
                    zysk_procent = (current_price - entry_price) / entry_price
                    if current_price > najwyzsza_cena_w_pozycji:
                        najwyzsza_cena_w_pozycji = current_price
                        zmieniono_stan = True
                    
                    if zysk_procent >= BREAKEVEN_PROCENT and virtual_sl < entry_price:
                        virtual_sl = entry_price * 1.0015 
                        zmieniono_stan = True
                        log_print(f"✨ Zabezpieczono pozycję na ZERO: {virtual_sl:.2f}")

                    if virtual_sl >= entry_price:
                        nowy_sl = najwyzsza_cena_w_pozycji * (1 - TRAILING_PROCENT)
                        if nowy_sl > virtual_sl:
                            virtual_sl = round(nowy_sl, 2)
                            zmieniono_stan = True
                            log_print(f"🔼 Trailing podciągnięty: {virtual_sl:.2f}")

                    if zmieniono_stan:
                        zapisz_stan_bota('LONG', entry_price, virtual_sl, najwyzsza_cena_w_pozycji, najnizsza_cena_w_pozycji, last_traded_candle_time, current_ml_snapshot)

                    if current_price <= virtual_sl:
                        pnl = (current_price - entry_price) * amt_abs
                        hl_exchange.market_close(hl_coin) 
                        msg = f"🏁 **{hl_coin} LONG ZAMKNIĘTY ({'ZYSK 🟢' if pnl>0 else 'STRATA 🔴'})**\nZysk: {pnl:+.2f} USDC"
                        wyslij_discord(msg); log_print(msg)
                        
                        zapisz_trade_do_bazy(hl_coin, "LONG", entry_price, current_price, pnl)
                        zapisz_trade_do_ml(current_ml_snapshot, pnl)
                        usun_stan_bota()
                        active_position_type = active_long = active_short = None 

                elif active_position_type == 'SHORT':
                    zysk_procent = (entry_price - current_price) / entry_price
                    if current_price < najnizsza_cena_w_pozycji:
                        najnizsza_cena_w_pozycji = current_price
                        zmieniono_stan = True

                    if zysk_procent >= BREAKEVEN_PROCENT and virtual_sl > entry_price:
                        virtual_sl = entry_price * 0.9985
                        zmieniono_stan = True
                        log_print(f"✨ Zabezpieczono pozycję na ZERO: {virtual_sl:.2f}")

                    if virtual_sl <= entry_price:
                        nowy_sl = najnizsza_cena_w_pozycji * (1 + TRAILING_PROCENT)
                        if nowy_sl < virtual_sl:
                            virtual_sl = round(nowy_sl, 2)
                            zmieniono_stan = True
                            log_print(f"🔽 Trailing podciągnięty: {virtual_sl:.2f}")

                    if zmieniono_stan:
                        zapisz_stan_bota('SHORT', entry_price, virtual_sl, najwyzsza_cena_w_pozycji, najnizsza_cena_w_pozycji, last_traded_candle_time, current_ml_snapshot)

                    if current_price >= virtual_sl:
                        pnl = (entry_price - current_price) * amt_abs
                        hl_exchange.market_close(hl_coin) 
                        msg = f"🏁 **{hl_coin} SHORT ZAMKNIĘTY ({'ZYSK 🟢' if pnl>0 else 'STRATA 🔴'})**\nZysk: {pnl:+.2f} USDC"
                        wyslij_discord(msg); log_print(msg)
                        
                        zapisz_trade_do_bazy(hl_coin, "SHORT", entry_price, current_price, pnl)
                        zapisz_trade_do_ml(current_ml_snapshot, pnl) 
                        usun_stan_bota()
                        active_position_type = active_long = active_short = None 

        # --- WYKRYWANIE SYGNAŁU ---
        if not active_position_type:
            if last_closed_candle['Time'] != last_traded_candle_time:
                if last_closed_candle['Is_Signal_Long']:
                    active_long = last_closed_candle['Entry_Long']
                elif last_closed_candle['Is_Signal_Short']:
                    active_short = last_closed_candle['Entry_Short']

        # --- WEJŚCIE I DECYZJA (DUAL-MODE AI) ---
        if active_long and current_price > active_long and not active_position_type:
            context_24h = pobierz_kontekst_24h(exchange, symbol_ccxt)
            dane_makro = pobierz_zaawansowane_dane(exchange, symbol_ccxt)
            zatwierdzono, powod = skonsultuj_z_ai(hl_coin, 'LONG', current_price, df.iloc[-25:-1], dane_makro, context_24h)
            
            if zatwierdzono:
                try:
                    user_state = hl_info.user_state(wallet_address)
                    balance = float(user_state.get("marginSummary", {}).get("accountValue", 0.0))
                    
                    hl_exchange.update_leverage(DZWIGNIA, hl_coin) 
                    dystans_do_sl = current_price * SL_PROCENT
                    
                    min_size = 0.01 if hl_coin == 'ETH' else 0.001
                    amount_coin = max(round((balance * 0.01) / dystans_do_sl, 4), min_size)

                    hl_exchange.market_open(hl_coin, True, amount_coin)
                    
                    current_ml_snapshot = {
                        'symbol': hl_coin, 'typ': 'LONG', 'cena': current_price,
                        'rsi': round(last_closed_candle['RSI'], 2), 'cvd': pobierz_aktualne_cvd(),
                        'trend_4h': dane_makro.get('ml_trend', 0), 'ob_ratio': dane_makro.get('ml_ob_ratio', 1.0)
                    }
                    
                    entry_price = current_price
                    last_traded_candle_time = last_closed_candle['Time']
                    najwyzsza_cena_w_pozycji = entry_price
                    virtual_sl = round(entry_price - dystans_do_sl, 2)   
                    active_position_type = 'LONG'
                    
                    zapisz_stan_bota('LONG', entry_price, virtual_sl, najwyzsza_cena_w_pozycji, najnizsza_cena_w_pozycji, last_traded_candle_time, current_ml_snapshot)
                    
                    msg = f"🟢 **{hl_coin} LONG OTWARTY**\nWejście: {entry_price} | SL: {virtual_sl}"
                    wyslij_discord(msg); log_print(msg)
                except Exception as e: log_print(f"❌ Błąd zlecenia LONG na HL: {e}")
            else:
                active_long = None
                last_traded_candle_time = last_closed_candle['Time']
            
        elif active_short and current_price < active_short and not active_position_type:
            context_24h = pobierz_kontekst_24h(exchange, symbol_ccxt)
            dane_makro = pobierz_zaawansowane_dane(exchange, symbol_ccxt)
            zatwierdzono, powod = skonsultuj_z_ai(hl_coin, 'SHORT', current_price, df.iloc[-25:-1], dane_makro, context_24h)
            
            if zatwierdzono:
                try:
                    user_state = hl_info.user_state(wallet_address)
                    balance = float(user_state.get("marginSummary", {}).get("accountValue", 0.0))
                    
                    hl_exchange.update_leverage(DZWIGNIA, hl_coin)
                    dystans_do_sl = current_price * SL_PROCENT
                    
                    min_size = 0.01 if hl_coin == 'ETH' else 0.001
                    amount_coin = max(round((balance * 0.01) / dystans_do_sl, 4), min_size)

                    hl_exchange.market_open(hl_coin, False, amount_coin)
                    
                    current_ml_snapshot = {
                        'symbol': hl_coin, 'typ': 'SHORT', 'cena': current_price,
                        'rsi': round(last_closed_candle['RSI'], 2), 'cvd': pobierz_aktualne_cvd(),
                        'trend_4h': dane_makro.get('ml_trend', 0), 'ob_ratio': dane_makro.get('ml_ob_ratio', 1.0)
                    }
                    
                    entry_price = current_price
                    last_traded_candle_time = last_closed_candle['Time']
                    najnizsza_cena_w_pozycji = entry_price
                    virtual_sl = round(entry_price + dystans_do_sl, 2)   
                    active_position_type = 'SHORT'
                    
                    zapisz_stan_bota('SHORT', entry_price, virtual_sl, najwyzsza_cena_w_pozycji, najnizsza_cena_w_pozycji, last_traded_candle_time, current_ml_snapshot)
                    
                    msg = f"🔴 **{hl_coin} SHORT OTWARTY**\nWejście: {entry_price} | SL: {virtual_sl}"
                    wyslij_discord(msg); log_print(msg)
                except Exception as e: log_print(f"❌ Błąd zlecenia SHORT na HL: {e}")
            else:
                active_short = None
                last_traded_candle_time = last_closed_candle['Time']

        # IDEALNY BALANS (3 sekundy) - Błyskawiczna reakcja bez banów API
        time.sleep(3)

    except Exception as e:
        log_print(f"[{datetime.now().strftime('%H:%M:%S')}] Błąd pętli bota na HL: {e}")
        time.sleep(5)
