# Autonomous AI Crypto Trading Bot

An autonomous algorithmic cryptocurrency trading bot built in Python using Google Gemini, designed for data-driven strategy execution and risk management on BTC/ETH markets.

## 🚀 Architecture & Core Features
*   **Modular Logic:** Independent execution scripts for BTC and ETH trading pairs (`bot.py`).
*   **Technical Indicators:** Real-time analysis utilizing RSI and dynamic threshold parameters.
*   **Risk Management:** Built-in safeguards against high volatility (focusing on extreme market conditions, e.g., RSI > 90).
*   **Local Persistence:** SQLite database integration (`*.db`) for robust trade history tracking.
*   **Automated Logging:** Daily rotating log system for continuous telemetry and debugging.

## 🛠️ Tech Stack
*   **Language:** Python 3.10+
*   **Environment:** Virtual Environment (`venv`)
*   **APIs:** Binance / Groq integrations for market data and execution.
*   **Version Control:** Git & GitHub

## ⚙️ Installation & Setup

1. Clone the repository:
   ```bash
   git clone [https://github.com/Kopertoja/Crypto-Bot.git](https://github.com/Kopertoja/Crypto-Bot.git)
   cd Crypto-Bot
2. Create and activate a virtual enviroment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
3. Instal dependencies:
   ```bash
   pip install -r requirements.txt
4. Configure enviroment variables:
   Create a .env file in root directory and add your credentials:
   API_KEY=your_binance_api_key
   API_SECRET=your_binance_api_secret
   GROQ_API_KEY=your_groq_api_key
   DISCORD_WEBHOOK_URL=your_discord_webhhok
5. Run:
   ```bash
   python3 bot.py
