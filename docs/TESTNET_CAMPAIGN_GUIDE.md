# Testnet Campaign Guide

## Overview

This guide provides step-by-step instructions for running a testnet campaign to forward-test the v2.1 bot before live deployment.

---

## Prerequisites

1. **Bybit Testnet Account**
   - Create account at https://testnet.bybit.com
   - Generate API keys (testnet keys, not live!)
   - Add to `.env` file:
     ```
     BYBIT_API_KEY=your_testnet_key
     BYBIT_API_SECRET=your_testnet_secret
     ```

2. **Testnet Funds**
   - Testnet provides free test funds
   - Verify you have sufficient balance

3. **Configuration**
   - Review `config/config.yaml`
   - Ensure `exchange.testnet: true`

---

## Campaign Setup

### Step 1: Configure Testnet

**Edit `.env`:**
```bash
BYBIT_API_KEY=your_testnet_api_key
BYBIT_API_SECRET=your_testnet_api_secret
```

**Verify Config:**
```yaml
exchange:
  testnet: true  # MUST be true for testnet
```

### Step 2: Choose Profile

**Recommended for First Campaign:**
- **Conservative**: Safest, lowest risk
- **Moderate**: Balanced risk/reward
- **Aggressive**: Higher risk (not recommended initially)

### Step 3: Run Campaign

**Option A: Fixed Duration (Recommended)**
```bash
# Run for 14 days
python scripts/run_testnet_campaign.py \
  --profile conservative \
  --duration-days 14
```

**Option B: Manual Stop**
```bash
# Run until Ctrl+C
python scripts/run_testnet_campaign.py \
  --profile conservative
```

**Option C: Direct Bot Run**
```bash
# Run bot directly (ensure testnet mode in config)
python live_bot.py --config config/config.yaml
```

---

## Monitoring During Campaign

### Check Status

**Status File:**
```bash
cat logs/bot_status.json | jq
```

**Recent Logs:**
```bash
tail -f logs/bot_*.log
```

**Health Status:**
```bash
cat logs/bot_status.json | jq '.health_status'
```

### What to Monitor

**Daily:**
- Health status (should be "HEALTHY")
- Trade count (should be reasonable, not zero)
- Performance guard status (should be "NORMAL" initially)

**Weekly:**
- Cumulative PnL
- Win rate
- Drawdown
- Any alerts

---

## Analyzing Results

### Step 1: Run Analysis Script

```bash
python scripts/analyse_testnet_results.py \
  --log-dir logs \
  --output logs/testnet_summary.md
```

### Step 2: Review Summary

**View Summary:**
```bash
cat logs/testnet_summary.md
```

**View Trade Data:**
```bash
cat logs/testnet_trades.csv
```

**View Daily Stats:**
```bash
cat logs/testnet_daily_stats.csv
```

---

## Interpreting Results

**Note:** See `docs/PHASE17_EXPERIMENT_RESULTS.md` for backtest results that can inform testnet expectations.

### Expected Testnet Performance (Based on Backtests)

**If backtests show:**
- Sharpe > 1.0, PF > 1.3, Win Rate > 50%
- **Testnet should show similar or slightly worse** (due to testnet limitations)

**If backtests show:**
- Sharpe 0.8-1.0, PF 1.2-1.3, Win Rate 45-50%
- **Testnet should show similar or slightly worse**

**If backtests show:**
- Sharpe < 0.8, PF < 1.2, Win Rate < 45%
- **Do NOT proceed to live** (even if testnet is good, backtests are more reliable)

---

## Interpreting Results

### "Good Enough" Indicators ✅

**Metrics to Look For:**
- **Sharpe Ratio**: > 0.8 (target: > 1.0)
- **Profit Factor**: > 1.2 (target: > 1.3)
- **Win Rate**: > 45% (target: > 50%)
- **Max Drawdown**: < 15% (target: < 12%)
- **Consistency**: Stable daily performance, no extreme swings

**Behavior:**
- Regular trading (not too few trades)
- Performance guard stays in NORMAL state
- No excessive alerts
- Health status remains HEALTHY

**Decision:** ✅ **Proceed to small live deployment**

---

### "Bad" Indicators ❌

**Metrics to Watch Out For:**
- **Sharpe Ratio**: < 0.5
- **Profit Factor**: < 1.0 (losing money)
- **Win Rate**: < 40%
- **Max Drawdown**: > 20%
- **High Volatility**: Large swings in daily PnL

**Behavior:**
- Performance guard frequently in REDUCED or PAUSED
- Many health issues
- Excessive alerts
- Very few trades (may indicate over-filtering)

**Decision:** ❌ **Do NOT proceed to live**

**Actions:**
1. Review config (may be too conservative or too aggressive)
2. Check logs for errors
3. Consider retraining model
4. Extend testnet campaign
5. Review market conditions (may be unfavorable)

---

### "Borderline" Indicators ⚠️

**Metrics:**
- Sharpe: 0.5 - 0.8
- Profit Factor: 1.0 - 1.2
- Win Rate: 40% - 45%
- Max Drawdown: 15% - 20%

**Decision:** ⚠️ **Extend testnet or proceed with extreme caution**

**Actions:**
1. Extend testnet to 3-4 weeks
2. Monitor closely
3. If improves, proceed with very small live capital
4. If degrades, review and adjust

---

## Campaign Duration Recommendations

### Minimum Duration
- **2 weeks** (14 days) - Absolute minimum
- **4 weeks** (28 days) - Recommended minimum

### Why Longer is Better
- More data points
- Exposure to different market conditions
- Better statistical significance
- More confidence in results

### When to Extend
- Metrics are borderline
- Market conditions are unusual
- Want more confidence
- First time running bot

---

## Common Issues & Solutions

### Issue: No Trades Executing

**Possible Causes:**
- Confidence threshold too high
- Regime filter blocking all trades
- Performance guard paused
- Portfolio selector (if enabled) not selecting symbols

**Solutions:**
1. Check logs for filtering reasons
2. Lower confidence threshold slightly
3. Check regime filter settings
4. Review performance guard status
5. Disable portfolio selector if needed

### Issue: Too Many Losing Trades

**Possible Causes:**
- Model not well-trained
- Market regime unfavorable
- Config too aggressive

**Solutions:**
1. Retrain model
2. Review market conditions
3. Use more conservative profile
4. Check if performance guard is throttling

### Issue: Performance Guard Frequently Paused

**Possible Causes:**
- Win rate too low
- Drawdown too high
- Losing streak

**Solutions:**
1. Review recent trades
2. Consider retraining model
3. Adjust performance guard thresholds (if too sensitive)
4. Review market conditions

### Issue: Health Issues

**Possible Causes:**
- Data feed stalled
- API errors
- Network issues

**Solutions:**
1. Check exchange status
2. Verify API keys
3. Check network connectivity
4. Restart bot if needed

---

## Decision Framework

### Proceed to Live If:
- ✅ Testnet duration: ≥ 2 weeks (preferably 4+)
- ✅ Sharpe ratio: > 0.8 consistently
- ✅ Profit factor: > 1.2 consistently
- ✅ Win rate: > 45%
- ✅ Max drawdown: < 15%
- ✅ Performance guard: Mostly NORMAL
- ✅ Health status: Mostly HEALTHY
- ✅ Trade count: Reasonable (not too few, not excessive)

### Do NOT Proceed If:
- ❌ Any critical metrics consistently poor
- ❌ Performance guard frequently paused
- ❌ Health issues unresolved
- ❌ Very few trades (may indicate over-filtering)
- ❌ Extreme volatility in results

### Proceed with Caution If:
- ⚠️ Metrics are borderline but improving
- ⚠️ Some periods good, some bad
- ⚠️ Want to test with very small capital first

---

## Next Steps After Testnet

### If Results Are Good:

1. **Prepare for Live:**
   - Review `docs/PRODUCTION_READINESS_CHECKLIST.md`
   - Set up live API keys (separate from testnet!)
   - Start with very small capital
   - Use conservative profile initially

2. **Initial Live Deployment:**
   - Start with $500-$1,000 (or equivalent)
   - Monitor daily for first week
   - Gradually increase if performance validates

3. **Scale Gradually:**
   - Only increase capital after validation
   - Monitor closely for first month
   - Keep size small until confident

### If Results Are Poor:

1. **Review and Adjust:**
   - Analyze what went wrong
   - Review config settings
   - Consider retraining model
   - Check market conditions

2. **Re-test:**
   - Make adjustments
   - Run another testnet campaign
   - Validate improvements

3. **Do NOT Deploy:**
   - Do not proceed to live if testnet is poor
   - Fix issues first
   - Validate fixes on testnet

---

## Example Campaign Timeline

### Week 1: Setup & Initial Run
- Day 1: Setup testnet account, configure bot
- Days 2-7: Run campaign, monitor daily

### Week 2: Monitoring
- Days 8-14: Continue campaign, weekly review

### Week 3-4: Extended Validation (Optional)
- Days 15-28: Extended campaign for more confidence

### After Campaign: Analysis
- Run analysis script
- Review results
- Make go/no-go decision

---

## Summary

**Testnet Campaign Process:**
1. ✅ Setup testnet account and API keys
2. ✅ Configure bot for testnet
3. ✅ Run campaign (minimum 2 weeks)
4. ✅ Monitor daily/weekly
5. ✅ Analyze results
6. ✅ Make go/no-go decision

**Key Principle:**
- **Never deploy to live without successful testnet validation**
- **Testnet results don't guarantee live performance, but poor testnet = don't deploy**

---

**Date:** December 2025  
**Version:** 2.1+  
**Status:** Production Guide

