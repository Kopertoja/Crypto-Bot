# 🚀 AI Crypto Trading Bot V6 (Hyperliquid Mainnet)

A fully autonomous, dual-mode algorithmic trading system for cryptocurrencies (BTC & ETH) on the **Hyperliquid** decentralized exchange. The system leverages technical analysis combined with an **AI Decision Matrix (Groq - GPT-OSS-120B)** to filter signals, protect capital, and avoid market traps such as spoofing.

---

## 🧠 Core Features

*   **Dual-Mode Strategy:** Two distinct market behavior profiles running concurrently:
    *   **BTC (Sniper / Mean Reversion):** Catches extreme market bottoms and tops (RSI < 30 / RSI > 70).
    *   **ETH (Trend Surfer):** Rides strong momentum breakouts and trend continuations (RSI > 60 / RSI < 40).
*   **AI Decision Matrix (Groq API):** Every technical signal is routed to a massive LLM (120B parameters) that analyzes macro trends (4H, 8H), Order Book imbalances, and 5-minute volume. The AI acts as a ruthless filter and has veto power to reject setups if it detects a trap.
*   **Live Order Flow (CVD):** Dedicated WebSockets listener tracking Binance Futures to extract real-time volume and CVD (Cumulative Volume Delta) for precision confirmation.
*   **"Pitbull" Risk Management:** 
    *   Dynamic position sizing (strict 1% account risk per trade).
    *   Hard Stop Loss: 3.0%.
    *   Fast Breakeven: Moves SL to +0.15% once a position hits 2.0% profit.
    *   Aggressive Trailing Stop: 1.5%.
*   **Black Box Recovery:** Real-time state persistence via `.json` tracking. In the event of a server restart or crash, the bot seamlessly resumes managing active positions without losing its memory.
*   **Automated Reporting:** Logs all trades to an SQLite database, generates a CSV dataset for future Machine Learning training, and sends weekly PnL reports (with charts) directly to a Discord Webhook.

---

## ⚙️ System Architecture

The system is designed to run on a Linux VPS (Ubuntu) using isolated services for maximum stability.
*   `bot-btc.service` - Dedicated process for BTC/USDC.
*   `bot-eth.service` - Dedicated process for ETH/USDC.
*   **Tech Stack:** Python 3, `ccxt` (Hyperliquid execution), `pandas`, `websockets`, `groq`, `sqlite3`, `matplotlib`, `eth_account`.

---

## 🛠️ Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/Kopertoja/Crypto-Bot.git](https://github.com/Kopertoja/Crypto-Bot.git)
   cd Crypto-Bot
2. **Create a virtual environment and install dependencies:**
    ```bash

    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

3. **Configure Environment Variables:**
    **Create a .env file in the root directory (this file is git-ignored for security):**
    Ini, TOML
   ```bash
    HL_WALLET_PRIVATE_KEY=your_hyperliquid_evm_private_key
    GROQ_API_KEY=your_groq_api_key
    DISCORD_WEBHOOK_URL=your_discord_webhook_url

4. **Run the bot:**
    ```bash

    python bot.py

(For production, it is highly recommended to run the bots via systemd services as described in the architecture section).

⚠️ Disclaimer

This source code is for educational and experimental purposes only. Trading cryptocurrencies with leverage carries a high level of risk and may not be suitable for all investors. This is not financial advice. Use at your own risk.
