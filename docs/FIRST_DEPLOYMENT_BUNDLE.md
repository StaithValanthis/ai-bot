# First Deployment Bundle

## Overview

This guide provides a **step-by-step path** from zero to a running testnet campaign, then to a tiny-size live deployment.

---

## Prerequisites

1. **Python Environment**
   - Python 3.8+
   - Dependencies installed (`pip install -r requirements.txt`)

2. **Bybit Accounts**
   - Testnet account: https://testnet.bybit.com
   - Live account (for later): https://www.bybit.com

3. **API Keys**
   - Testnet API keys (from testnet account)
   - Live API keys (from live account) - **Keep separate!**

---

## Step 1: Initial Setup (One-Time)

### 1.1 Automated Installation (Recommended)

**Use the one-shot installer:**

```bash
# Clone repo (if not already done)
git clone <repo-url>
cd ai-bot

# Run installer
bash install.sh
```

The installer will:
- ✅ Install system dependencies (Python, build tools, etc.)
- ✅ Create Python virtual environment
- ✅ Install all Python packages
- ✅ Prompt for Bybit API keys interactively
- ✅ Configure `.env` file automatically
- ✅ Optionally set up systemd services
- ✅ Guide you through next steps

**Note:** The installer does **NOT** automatically start trading. You still need to:
- Fetch historical data
- Train models
- Run testnet campaigns
- Manually start the bot when ready

### 1.2 Manual Setup (Alternative)

If you prefer manual setup or are not on Ubuntu/Debian:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file manually
cat > .env <<EOF
BYBIT_API_KEY=your_testnet_api_key
BYBIT_API_SECRET=your_testnet_api_secret
BYBIT_TESTNET=true
DEFAULT_PROFILE=profile_conservative
EOF
```

### 1.3 Verify Config

**Check `config/config.yaml`:**
- `exchange.testnet: true` (for testnet)
- `trading.symbols: ["BTCUSDT"]` (start with one symbol)
- Risk settings are conservative

**Check `.env` file:**
- API keys are set correctly
- `BYBIT_TESTNET=true` for initial testing
- `DEFAULT_PROFILE=profile_conservative` (recommended)

---

## Step 2: Fetch Historical Data

### 2.1 Download Data for Training

```bash
# Fetch 2 years of BTCUSDT data
python scripts/fetch_and_check_data.py \
  --symbol BTCUSDT \
  --years 2 \
  --timeframe 60

# Check quality report
cat logs/data_quality_BTCUSDT_60.md
```

**Expected Output:**
- ✅ Data downloaded successfully
- ✅ Quality checks passed (or minor warnings)
- Data saved to `data/raw/bybit/BTCUSDT_60.parquet`

### 2.2 Verify Data Quality

**Review quality report:**
- Should show: ✅ PASSED
- Issues: 0 (or very few)
- Warnings: Acceptable (gaps are normal)

**If issues found:**
- Re-download: `--force-redownload`
- Review logs: `logs/fetch_data_*.log`
- Fix critical issues before proceeding

---

## Step 3: Train Initial Model

### 3.1 Train Model

```bash
# Train model on downloaded data
python train_model.py \
  --symbol BTCUSDT \
  --years 2
```

**Expected Output:**
- Model trained successfully
- Saved to `models/`
- Training metrics displayed

### 3.2 Verify Model

**Check model files:**
```bash
ls models/
# Should see:
# - meta_model_v1.0.joblib
# - feature_scaler_v1.0.joblib
# - model_config_v1.0.json
```

---

## Step 4: Testnet Campaign (2-4 Weeks)

### 4.1 Start Testnet Campaign

```bash
# Run testnet campaign for 14 days
python scripts/run_testnet_campaign.py \
  --profile conservative \
  --duration-days 14
```

**Or run until manually stopped:**
```bash
python scripts/run_testnet_campaign.py \
  --profile conservative
# Press Ctrl+C to stop
```

### 4.2 Monitor During Campaign

**Check status:**
```bash
# Quick status check
python scripts/show_status.py

# Or view raw status
cat logs/bot_status.json | jq
```

**Monitor logs:**
```bash
# Watch logs in real-time
tail -f logs/bot_*.log
```

**What to Monitor:**
- Health status (should be HEALTHY)
- Trade count (should be reasonable)
- Performance guard (should be NORMAL)
- No excessive errors

### 4.3 Analyze Results

**After campaign ends:**
```bash
# Analyze testnet results
python scripts/analyse_testnet_results.py \
  --log-dir logs \
  --output logs/testnet_summary.md
```

**Review summary:**
```bash
cat logs/testnet_summary.md
```

**Decision Criteria:**
- ✅ **Proceed to Live**: Sharpe > 0.8, PF > 1.2, Win Rate > 45%, Max DD < 15%
- ⚠️ **Extend Testnet**: Metrics borderline, extend to 3-4 weeks
- ❌ **Do NOT Proceed**: Metrics poor, review config, retrain model

---

## Step 5: Tiny-Size Live Deployment

### 5.1 Prepare for Live

**⚠️ CRITICAL: Only proceed if testnet was successful!**

1. **Switch to Live API Keys:**
   ```bash
   # Update .env with LIVE keys (not testnet!)
   BYBIT_API_KEY=your_live_api_key
   BYBIT_API_SECRET=your_live_api_secret
   ```

2. **Update Config:**
   ```yaml
   exchange:
     testnet: false  # ⚠️ MUST be false for live!
   ```

3. **Verify Risk Settings:**
   - Use conservative profile
   - Start with minimal capital ($500-$1,000)
   - Max leverage: 2x
   - Max position size: 5%

### 5.2 Start Live Bot

```bash
# Start live bot
python live_bot.py --config config/config.yaml
```

**Or use systemd (recommended for long-term):**
```bash
# See docs/PHASE19_DEPLOYMENT_SCENARIO.md for systemd setup
sudo systemctl start bybit-bot
```

### 5.3 Monitor Closely (First Week)

**Daily checks:**
```bash
# Check status
python scripts/show_status.py

# Review recent trades
tail -20 logs/bot_*.log | grep "Trade closed"

# Check for alerts
grep "\[ALERT\]" logs/bot_*.log | tail -10
```

**What to Watch:**
- Health status
- Trade execution
- Performance guard status
- Any errors or alerts

---

## Step 6: Scale Gradually (After Validation)

### 6.1 After 1 Week

**If performance is good:**
- Continue monitoring
- Review weekly performance
- Consider adding second symbol (ETHUSDT)

**If performance is poor:**
- Stop bot
- Review logs and config
- Consider retraining model
- Re-test on testnet

### 6.2 After 1 Month

**If consistently good:**
- Consider moderate profile (if desired)
- Gradually increase capital (if comfortable)
- Enable auto-retraining (if desired)

**Always:**
- Keep size small
- Monitor regularly
- Stay within risk limits

---

## Safety Checklist

### Before Testnet
- [ ] Testnet API keys configured
- [ ] Config set to testnet mode
- [ ] Data downloaded and quality-checked
- [ ] Model trained and verified
- [ ] Conservative profile selected

### Before Live
- [ ] Testnet campaign successful (2+ weeks)
- [ ] Metrics meet criteria (Sharpe > 0.8, PF > 1.2, etc.)
- [ ] Live API keys configured (separate from testnet!)
- [ ] Config set to live mode (`testnet: false`)
- [ ] Risk settings conservative
- [ ] Starting with minimal capital
- [ ] Monitoring plan in place
- [ ] Alerts configured (if desired)

### During Live
- [ ] Monitor daily (first week)
- [ ] Check status regularly
- [ ] Review trades weekly
- [ ] Respond to alerts promptly
- [ ] Stay within risk limits
- [ ] Keep size small

---

## Quick Reference Commands

### Data Management
```bash
# Fetch data
python scripts/fetch_and_check_data.py --symbol BTCUSDT --years 2

# Check data quality
cat logs/data_quality_BTCUSDT_60.md
```

### Training
```bash
# Train model
python train_model.py --symbol BTCUSDT --years 2
```

### Testnet
```bash
# Run testnet campaign
python scripts/run_testnet_campaign.py --profile conservative --duration-days 14

# Analyze results
python scripts/analyse_testnet_results.py
```

### Live
```bash
# Check status
python scripts/show_status.py

# Start bot
python live_bot.py

# View logs
tail -f logs/bot_*.log
```

---

## Troubleshooting

### Issue: No Trades in Testnet

**Check:**
1. Confidence threshold (may be too high)
2. Regime filter (may be blocking)
3. Performance guard (may be paused)
4. Market conditions (may be unfavorable)

**Solutions:**
- Lower confidence threshold slightly
- Check regime filter settings
- Review performance guard status
- Wait for better market conditions

### Issue: Poor Testnet Performance

**Check:**
1. Model quality (retrain if needed)
2. Config settings (may be too aggressive)
3. Market conditions (may be unfavorable)

**Solutions:**
- Retrain model
- Use more conservative settings
- Extend testnet campaign
- Review market conditions

### Issue: Bot Stops Unexpectedly

**Check:**
1. Logs: `tail -100 logs/bot_*.log`
2. Status: `python scripts/show_status.py`
3. Health: `cat logs/bot_status.json | jq`

**Solutions:**
- Review logs for errors
- Check API connectivity
- Verify config is correct
- Restart if needed

---

## Important Reminders

1. **Always Start on Testnet**
   - Never skip testnet validation
   - Minimum 2 weeks testnet before live

2. **Keep Size Small**
   - Start with minimal capital
   - Scale gradually only after validation
   - Never risk more than you can afford to lose

3. **Monitor Closely**
   - First week: Daily checks
   - First month: Weekly reviews
   - Ongoing: Regular monitoring

4. **No Guarantees**
   - Trading involves risk
   - Losses are possible
   - Past performance ≠ future results

---

## Next Steps After First Deployment

1. **After Successful Testnet:**
   - Proceed to tiny-size live
   - Monitor closely
   - Scale gradually

2. **After Successful Live (1 Month):**
   - Consider adding symbols
   - Consider moderate profile (if desired)
   - Enable auto-retraining
   - Continue monitoring

3. **Ongoing:**
   - Regular performance reviews
   - Periodic model retraining
   - Config adjustments (if needed)
   - Stay informed about market conditions

---

## Summary

**Deployment Path:**
1. ✅ Setup environment
2. ✅ Fetch and validate data
3. ✅ Train model
4. ✅ Run testnet campaign (2-4 weeks)
5. ✅ Analyze results
6. ✅ Deploy to live (tiny size, if testnet successful)
7. ✅ Monitor closely
8. ✅ Scale gradually

**Key Principle:**
- **Never skip testnet validation**
- **Start small, scale gradually**
- **Monitor closely, especially early on**

---

**Date:** December 2025  
**Version:** 2.1+  
**Status:** Deployment Guide

