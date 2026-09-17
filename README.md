# 🚀 AI Crypto Trading Bot V6 (Hyperliquid Mainnet)

W pełni autonomiczny, podwójny system algorytmiczny do handlu kryptowalutami (BTC i ETH) na giełdzie zdecentralizowanej **Hyperliquid**. System wykorzystuje analizę techniczną połączoną z **Matrycą Decyzyjną AI (Groq - GPT-OSS-120B)** w celu filtrowania sygnałów, ochrony kapitału i unikania pułapek rynkowych (spoofing).

---

## 🧠 Główne funkcjonalności

*   **Dual-Mode Strategy:** Dwa oddzielne profile zachowań na rynku:
    *   **BTC (Sniper / Mean Reversion):** Łapie ekstremalne dołki i szczyty (RSI < 30 / RSI > 70).
    *   **ETH (Trend Surfer):** Podłącza się pod silne momentum (RSI > 60 / RSI < 40).
*   **AI Decision Matrix (Groq API):** Każdy sygnał z wykresu jest wysyłany do potężnego modelu językowego (120B parametrów), który analizuje trend makro (4H, 8H), dysproporcję Order Booka oraz wolumen z 5m. AI ma prawo zawetować trade, jeśli wykryje pułapkę.
*   **Live Order Flow (CVD):** Moduł nasłuchujący WebSockets z Binance Futures dla uzyskania precyzyjnego wolumenu i CVD (Cumulative Volume Delta) w czasie rzeczywistym.
*   **Zarządzanie ryzykiem "Pitbull":** 
    *   Dynamiczna wielkość pozycji (ryzyko 1% kapitału).
    *   Sztywny Stop Loss: 3%.
    *   Szybki Breakeven (przestawienie na +0.15% po zysku 2%).
    *   Agresywny Trailing Stop (1.5%).
*   **Black Box Recovery:** Moduł zapisujący na bieżąco stan bota do plików `.json`. W przypadku restartu serwera lub utraty zasilania, bot automatycznie wznawia prowadzenie otwartej pozycji.
*   **Automatyczne Raportowanie:** Zapis każdego zagrania do bazy SQLite i wysyłanie tygodniowych raportów PnL (z wykresem) na Discorda via Webhook. Tworzy również dataset CSV do późniejszego uczenia maszynowego.

---

## ⚙️ Architektura Systemu

System działa na serwerze VPS (Ubuntu) w izolowanych usługach systemowych.
*   `bot-btc.service` - nasłuchuje i traduje na rynku BTC/USDC.
*   `bot-eth.service` - nasłuchuje i traduje na rynku ETH/USDC.
*   **Biblioteki:** `ccxt` (Hyperliquid), `pandas`, `websockets`, `groq`, `sqlite3`, `matplotlib`.

---

## 🛠️ Instalacja i konfiguracja

1. Klonowanie repozytorium:
   ```bash
   git clone [https://github.com/TWOJ_NICK/Crypto-Bot.git](https://github.com/TWOJ_NICK/Crypto-Bot.git)
   cd Crypto-Bot
