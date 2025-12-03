# Quick Start Guide

## Prerequisites

1. Python 3.10+
2. Bybit testnet account (get free API keys at https://testnet.bybit.com/)

## Setup Steps

### Option 1: Automated Installer (Recommended for Ubuntu/Debian)

```bash
git clone <repo-url>
cd ai-bot
bash install.sh
```

The installer will:
- Install system dependencies
- Set up Python virtual environment
- Install Python packages
- Prompt for API keys and configuration
- Create `.env` file automatically

**See `docs/FIRST_DEPLOYMENT_BUNDLE.md` for complete setup guide.**

### Option 2: Manual Setup

#### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

#### 2. Configure API Keys

Create a `.env` file in the project root:

```bash
BYBIT_API_KEY=your_testnet_api_key
BYBIT_API_SECRET=your_testnet_api_secret
BYBIT_TESTNET=true
DEFAULT_PROFILE=profile_conservative
```

**Get testnet keys**: https://testnet.bybit.com/

### 3. Train the Model

```bash
python train_model.py --symbol BTCUSDT --days 730
```

This will:
- Download 730 days of historical data
- Train the meta-model
- Save model to `models/`

**Expected time**: 10-30 minutes (depending on data download speed)

### 4. Run the Bot (Testnet)

```bash
python live_bot.py
```

The bot will:
- Load the trained model
- Connect to Bybit WebSocket
- Start generating signals and trading

**Stop**: Press `Ctrl+C`

## Monitoring

Check logs in `logs/` directory:
- `logs/trades_YYYYMMDD.jsonl` - Trade logs
- `logs/bot_YYYYMMDD.log` - Bot activity

## Troubleshooting

### "Model file not found"
→ Train the model first: `python train_model.py`

### "Invalid API key"
→ Check your `.env` file has correct testnet API keys

### "No data downloaded"
→ Check internet connection and Bybit API status

## Next Steps

1. **Paper Trade**: Run on testnet for at least 1-2 weeks
2. **Monitor Performance**: Check logs and PnL
3. **Adjust Parameters**: Edit `config/config.yaml` if needed
4. **Retrain Model**: Periodically retrain with new data

## Important Notes

- ⚠️ **Always start with testnet**
- ⚠️ **Use small position sizes initially**
- ⚠️ **Monitor closely for the first few days**
- ⚠️ **Never risk more than you can afford to lose**

