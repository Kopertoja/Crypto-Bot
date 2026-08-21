import os
import time
from datetime import datetime, timedelta
import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
import ccxt
import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET
import re
import json
import sqlite3
import matplotlib.pyplot as plt
from groq import Groq

# Wczytujemy zmienne
load_dotenv()
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_API_SECRET')
WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# ==========================================
# 1. BAZA DANYCH I RAPORTY (MATPLOTLIB) - WERSJA ETH
# ==========================================
def setup_db():
    conn = sqlite3.connect('trades_history_eth.db') # ZMIANA: Osobna baza dla ETH
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
        log_print("📊 Generowanie raportu tygodniowego ETH...")
        df_db = pd.read_sql_query("SELECT * FROM trades", db_conn)
        
        if df_db.empty:
            wyslij_discord("📊 **Raport Tygodniowy ETH:** Brak transakcji w bazie.")
            return

        df_db['date'] = pd.to_datetime(df_db['date'])
        tydzien_temu = datetime.now() - timedelta(days=7)
        df_tydzien = df_db[df_db['date'] >= tydzien_temu]

        if df_tydzien.empty:
            wyslij_discord("📊 **Raport Tygodniowy ETH:** Brak nowych transakcji w tym tygodniu.")
            return

        win_rate = (len(df_tydzien[df_tydzien['pnl'] > 0]) / len(df_tydzien)) * 100
        total_pnl = df_tydzien['pnl'].sum()
        
        plt.figure(figsize=(10, 5))
        df_tydzien['cumulative_pnl'] = df_tydzien['pnl'].cumsum()
        plt.plot(df_tydzien['date'], df_tydzien['cumulative_pnl'], marker='o', linestyle='-', color='g') # ZMIANA: Kolor zielony dla ETH
        plt.title(f'Tygodniowy PnL ETH ({total_pnl:+.2f} USDT)')
        plt.xlabel('Data')
        plt.ylabel('Skumulowany Zysk (USDT)')
        plt.grid(True)
        plt.tight_layout()
        plt.savefig('raport_tygodniowy_eth.png') # ZMIANA: Osobny plik obrazka
        plt.close()

        wiadomosc = (f"📈 **RAPORT TYGODNIOWY ETH (V4)** 📈\n"
                     f"Liczba trade'ów: {len(df_tydzien)}\n"
                     f"Skuteczność (Win-Rate): **{win_rate:.1f}%**\n"
                     f"Zysk Netto: **{total_pnl:+.2f} USDT**")
        
        with open('raport_tygodniowy_eth.png', 'rb') as f:
            requests.post(WEBHOOK_URL, data={'payload_json': json.dumps({"content": wiadomosc})}, files={'file': f})
        log_print("✅ Raport tygodniowy ETH wysłany!")
    except Exception as e:
        log_print(f"❌ Błąd przy generowaniu raportu: {e}")

# ==========================================
# 2. DISCORD & LOGI - WERSJA ETH
# ==========================================
def wyslij_discord(wiadomosc):
    if not WEBHOOK_URL: return
    try: requests.post(WEBHOOK_URL, json={"content": wiadomosc}, timeout=5)
    except: pass

logger = logging.getLogger("crypto_bot_eth_v4") # ZMIANA: Nazwa loggera
logger.setLevel(logging.INFO)
if not logger.handlers:
    file_handler = TimedRotatingFileHandler('bot_eth_log.txt', when='midnight', interval=1, backupCount=7, encoding='utf-8') # ZMIANA: Plik logów
    file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(file_handler)

def log_print(message):
    print(message, flush=True); logger.info(message)        

# ==========================================
# 3. ZAAWANSOWANE ZBIERANIE DANYCH (ETH)
# ==========================================
client = Groq(api_key=GROQ_API_KEY)

def pobierz_fear_and_greed():
    try:
        data = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5).json()
        return f"{data['data'][0]['value']}/100 ({data['data'][0]['value_classification']})"
    except: return "Brak danych"

def pobierz_newsy_krypto():
    try:
        url = "https://cointelegraph.com/rss/tag/ethereum" # ZMIANA: Tag Ethereum
        response = requests.get(url, timeout=5)
        root = ET.fromstring(response.content)
        newsy = []
        for item in root.findall('./channel/item')[:5]:
            title = item.find('title').text
            clean_desc = re.sub(r'<[^>]+>', '', item.find('description').text).strip()
            newsy.append(f"Tytuł: {title} | Streszczenie: {clean_desc}")
        return newsy
    except: return ["Brak wiadomości (błąd sieci)."]

def pobierz_zaawansowane_dane(exchange, symbol):
    dane_makro = {}
    try:
        ohlcv_4h = exchange.fetch_ohlcv(symbol, '4h', limit=200)
        df_4h = pd.DataFrame(ohlcv_4h, columns=['Timestamp', 'O', 'H', 'L', 'C', 'V'])
        ema_200 = df_4h['C'].ewm(span=200, adjust=False).mean().iloc[-1]
        cena_4h = df_4h['C'].iloc[-1]
        dane_makro['trend_4h'] = "UPTREND (Hossa)" if cena_4h > ema_200 else "DOWNTREND (Bessa)"
        
        ob = exchange.fetch_order_book(symbol, limit=50)
        bids_volume = sum([bid[1] for bid in ob['bids']])
        asks_volume = sum([ask[1] for ask in ob['asks']])
        dane_makro['ob_imbalance'] = f"Popyt(Kupcy): {bids_volume:.1f} ETH vs Podaż(Sprzedawcy): {asks_volume:.1f} ETH"

        try:
            funding = exchange.fetch_funding_rate(symbol)
            dane_makro['funding'] = f"{funding['fundingRate'] * 100:.4f}%"
        except: dane_makro['funding'] = "Brak danych"

    except Exception as e:
        log_print(f"⚠️ Błąd pobierania zaawansowanych danych: {e}")
        dane_makro['trend_4h'] = "Nieznany"; dane_makro['ob_imbalance'] = "Brak danych"; dane_makro['funding'] = "Brak danych"
        
    return dane_makro

def skonsultuj_z_ai(symbol, typ_sygnalu, current_price, df_kontekst, makro_dane):
    log_print("  🧠 Łączę dane 15m, 4H, Order Book i Sentyment ETH. Wysyłam do AI...")
    fng = pobierz_fear_and_greed()
    newsy_tekst = "\n".join([f"- {n}" for n in pobierz_newsy_krypto()])
    historia_cen = df_kontekst[['Time', 'Close', 'Volume', 'RSI']].to_dict(orient='records')
    
    prompt = f"""
    Jako elitarny algorytm kwantowy, decydujesz o otwarciu transakcji.
    Sygnał techniczny (15m): {typ_sygnalu} po cenie {current_price}.
    
    [DANE TECHNICZNE 15m]: {historia_cen}
    
    [DANE MAKRO I GIEŁDOWE DLA ETH]:
    - Główny trend rynkowy (wykres 4H): {makro_dane['trend_4h']}
    - Fear & Greed Index: {fng}
    - Przewaga w Order Booku (najbliższe zlecenia): {makro_dane['ob_imbalance']}
    - Funding Rate (Koszty utrzymania pozycji): {makro_dane['funding']}
    - Najnowsze newsy o ETH:
    {newsy_tekst}
    
    Oceń to wszystko. Zwróć WYŁĄCZNIE poprawny JSON:
    {{
        "decyzja": "TAK" lub "NIE", 
        "powod": "Krótkie analityczne zdanie wyjaśniające decyzję, uwzględniające newsy ETH, trend 4H i Order Book"
    }}
    """
    try:
        res = client.chat.completions.create(
            messages=[{"role": "system", "content": "Zwracaj tylko poprawny JSON."},
                      {"role": "user", "content": prompt}],
            model="openai/gpt-oss-120b", temperature=0.1, response_format={"type": "json_object"}
        )
        wynik = json.loads(res.choices[0].message.content)
        return wynik.get('decyzja') == "TAK", wynik.get('powod', 'Brak powodu')
    except Exception as e:
        return False, f"Błąd AI: {e}"

# ==========================================
# 4. GŁÓWNA PĘTLA - ETH
# ==========================================
exchange = ccxt.binance({
    'apiKey': API_KEY, 'secret': SECRET_KEY,
    'enableRateLimit': True, 'options': {'defaultType': 'future'},
})
exchange.enable_demo_trading(True)

symbol = 'ETH/USDT' # ZMIANA: ETH
timeframe = '15m'
WINDOW = 20
MULTIPLIER = 2.0
VOL_MULTIPLIER = 1.5

log_print(f"🚀 BOTA V4 (GOD MODE) dla {symbol} URUCHOMIONO!")
wyslij_discord(f"🚀 **V4 STARTED**: {symbol} | Dodano: Order Book, Trend 4H, Funding Rate, Tygodniowe Wykresy SQLite!")

active_long, active_short = None, None
active_position_type, virtual_tp, virtual_sl, entry_price = None, None, None, None
last_traded_candle_time = None
najwyzsza_cena_w_pozycji, najnizsza_cena_w_pozycji = None, None
ostatni_raport_tydzien = -1 
heartbeat_counter = 0

while True:
    try:
        now = datetime.now()
        
        # WYSYŁANIE RAPORTÓW (Niedziela, 20:00)
        if now.weekday() == 6 and now.hour == 20 and now.isocalendar()[1] != ostatni_raport_tydzien:
            generuj_i_wyslij_raport_tygodniowy()
            ostatni_raport_tydzien = now.isocalendar()[1]

        # POBIERANIE WSKAŹNIKÓW (15m)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['Time'] = pd.to_datetime(df['Timestamp'], unit='ms').dt.strftime('%H:%M')
        
        # RSI & ATR
        delta = df['Close'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        df['RSI'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / down.ewm(com=13, adjust=False).mean())))
        tr1 = df['High'] - df['Low']
        tr2 = (df['High'] - df['Close'].shift(1)).abs()
        tr3 = (df['Low'] - df['Close'].shift(1)).abs()
        df['ATR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()

        # Logika Wybicia
        df['Candle_Length'] = df['High'] - df['Low']
        df['Avg_Length'] = df['Candle_Length'].shift(1).rolling(WINDOW).mean()
        df['Avg_Volume'] = df['Volume'].shift(1).rolling(WINDOW).mean()
        
        df['Is_Signal_Long'] = (df['Candle_Length'] > (df['Avg_Length'] * MULTIPLIER)) & (df['Volume'] > (df['Avg_Volume'] * VOL_MULTIPLIER)) & (df['RSI'] < 70) 
        df['Is_Signal_Short'] = (df['Candle_Length'] > (df['Avg_Length'] * MULTIPLIER)) & (df['Volume'] > (df['Avg_Volume'] * VOL_MULTIPLIER)) & (df['RSI'] > 30)
                                 
        df['Entry_Long'] = np.where(df['Is_Signal_Long'], df['High'], np.nan)
        df['Entry_Short'] = np.where(df['Is_Signal_Short'], df['Low'], np.nan)
        
        last_closed_candle, current_candle = df.iloc[-2], df.iloc[-1]
        current_price, current_atr = current_candle['Close'], current_candle['ATR']
        
        is_allowed_time = True
        heartbeat_counter += 1
        if heartbeat_counter % 60 == 0:
            log_print(f" [HEARTBEAT] Bot {symbol} działa i skanuje. Aktualna cena: {current_price:.2f}")
        
        # ==========================================
        # ZARZĄDZANIE POZYCJĄ (TRAILING STOP)
        # ==========================================
        if active_position_type:
            positions = exchange.fetch_positions([symbol])
            position_amt = float(next((pos['info']['positionAmt'] for pos in positions if float(pos['info']['positionAmt']) != 0.0), 0.0))
            
            if position_amt == 0.0:
                log_print("ℹ️ Pozycja zamknięta ręcznie.")
                active_position_type = active_long = active_short = None
            else:
                amt_abs = abs(position_amt)
                if active_position_type == 'LONG':
                    if current_price > najwyzsza_cena_w_pozycji:
                        najwyzsza_cena_w_pozycji = current_price
                        nowy_sl = najwyzsza_cena_w_pozycji - (current_atr * 1.5)
                        if nowy_sl > virtual_sl:
                            virtual_sl = round(nowy_sl, 2)
                            log_print(f"🔼 Trailing SL: {virtual_sl:.2f}")

                    if current_price <= virtual_sl or current_price >= virtual_tp:
                        pnl = (current_price - entry_price) * amt_abs
                        exchange.create_market_sell_order(symbol, amt_abs)
                        msg = f"🏁 **ETH LONG ZAMKNIĘTY ({'ZYSK 🟢' if pnl>0 else 'STRATA 🔴'})**\nZysk: {pnl:+.2f} USDT"
                        wyslij_discord(msg); log_print(msg)
                        zapisz_trade_do_bazy(symbol, "LONG", entry_price, current_price, pnl)
                        active_position_type = active_long = active_short = None 

                elif active_position_type == 'SHORT':
                    if current_price < najnizsza_cena_w_pozycji:
                        najnizsza_cena_w_pozycji = current_price
                        nowy_sl = najnizsza_cena_w_pozycji + (current_atr * 1.5)
                        if nowy_sl < virtual_sl:
                            virtual_sl = round(nowy_sl, 2)
                            log_print(f"🔽 Trailing SL: {virtual_sl:.2f}")

                    if current_price >= virtual_sl or current_price <= virtual_tp:
                        pnl = (entry_price - current_price) * amt_abs
                        exchange.create_market_buy_order(symbol, amt_abs)
                        msg = f"🏁 **ETH SHORT ZAMKNIĘTY ({'ZYSK 🟢' if pnl>0 else 'STRATA 🔴'})**\nZysk: {pnl:+.2f} USDT"
                        wyslij_discord(msg); log_print(msg)
                        zapisz_trade_do_bazy(symbol, "SHORT", entry_price, current_price, pnl)
                        active_position_type = active_long = active_short = None 

        # ==========================================
        # WYKRYWANIE SYGNAŁU 15m
        # ==========================================
        if is_allowed_time and not active_position_type:
            if last_closed_candle['Time'] != last_traded_candle_time:
                if last_closed_candle['Is_Signal_Long']:
                    active_long = last_closed_candle['Entry_Long']
                    log_print(f"  >>> SYGNAŁ LONG! (RSI: {last_closed_candle['RSI']:.2f}) Bariera > {active_long:.2f}")
                elif last_closed_candle['Is_Signal_Short']:
                    active_short = last_closed_candle['Entry_Short']
                    log_print(f"  >>> SYGNAŁ SHORT! (RSI: {last_closed_candle['RSI']:.2f}) Bariera < {active_short:.2f}")

        # ==========================================
        # WEJŚCIE I DECYZJA (Multi-Timeframe + OrderBook)
        # ==========================================
        if active_long and current_price > active_long and not active_position_type:
            log_print(f"  🟢 Bariera LONG pękła. Pobieram dane kwantowe ETH (4H, OrderBook)...")
            
            dane_makro = pobierz_zaawansowane_dane(exchange, symbol)
            zatwierdzono, powod = skonsultuj_z_ai(symbol, 'LONG', current_price, df.iloc[-25:-1], dane_makro)
            
            if zatwierdzono:
                try:
                    balance = exchange.fetch_balance()['USDT']['free']
                    ryzykowany_kapital = balance * 0.01 
                    dystans_do_sl = last_closed_candle['ATR'] * 1.5
                    amount_eth = max(round(ryzykowany_kapital / dystans_do_sl, 3), 0.001) # ZMIANA: amount_eth

                    exchange.create_market_buy_order(symbol, amount_eth)
                    
                    entry_price = current_price
                    last_traded_candle_time = last_closed_candle['Time']
                    najwyzsza_cena_w_pozycji = entry_price
                    virtual_sl = round(entry_price - dystans_do_sl, 2)   
                    virtual_tp = round(entry_price + (last_closed_candle['ATR'] * 3.0), 2)  
                    active_position_type = 'LONG'
                    
                    msg = (f"🟢 **ETH LONG OTWARTY (AI V4)**\nZrozumienie Rynku: *{powod}*\n"
                           f"Wejście: {entry_price} | TP: {virtual_tp} | SL: {virtual_sl}")
                    wyslij_discord(msg); log_print(msg)
                except Exception as e: log_print(f"❌ Błąd zlecenia LONG: {e}")
            else:
                log_print(f"  🛑 AI VETO: {powod}. Anuluję trade."); active_long = None
            
        elif active_short and current_price < active_short and not active_position_type:
            log_print(f"  🔴 Bariera SHORT pękła. Pobieram dane kwantowe ETH (4H, OrderBook)...")
            
            dane_makro = pobierz_zaawansowane_dane(exchange, symbol)
            zatwierdzono, powod = skonsultuj_z_ai(symbol, 'SHORT', current_price, df.iloc[-25:-1], dane_makro)
            
            if zatwierdzono:
                try:
                    balance = exchange.fetch_balance()['USDT']['free']
                    ryzykowany_kapital = balance * 0.01 
                    dystans_do_sl = last_closed_candle['ATR'] * 1.5
                    amount_eth = max(round(ryzykowany_kapital / dystans_do_sl, 3), 0.001) # ZMIANA: amount_eth

                    exchange.create_market_sell_order(symbol, amount_eth)
                    
                    entry_price = current_price
                    last_traded_candle_time = last_closed_candle['Time']
                    najnizsza_cena_w_pozycji = entry_price
                    virtual_sl = round(entry_price + dystans_do_sl, 2)   
                    virtual_tp = round(entry_price - (last_closed_candle['ATR'] * 3.0), 2)  
                    active_position_type = 'SHORT'
                    
                    msg = (f"🔴 **ETH SHORT OTWARTY (AI V4)**\nZrozumienie Rynku: *{powod}*\n"
                           f"Wejście: {entry_price} | TP: {virtual_tp} | SL: {virtual_sl}")
                    wyslij_discord(msg); log_print(msg)
                except Exception as e: log_print(f"❌ Błąd zlecenia SHORT: {e}")
            else:
                log_print(f"  🛑 AI VETO: {powod}. Anuluję trade."); active_short = None

        time.sleep(15)

    except Exception as e:
        log_print(f"[{datetime.now().strftime('%H:%M:%S')}] Błąd sieci/API: {e}")
        time.sleep(15)
