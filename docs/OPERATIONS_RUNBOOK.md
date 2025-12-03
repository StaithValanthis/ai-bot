# Operations Runbook

## Overview

This runbook provides operational procedures for running and maintaining the v2.1 Bybit AI trading bot in production.

---

## Using install.sh for a New Server

### Quick Setup

For a fresh Ubuntu/Debian server, the fastest path is:

1. **Clone repository:**
   ```bash
   git clone <repo-url>
   cd ai-bot
   ```

2. **Run installer:**
   ```bash
   bash install.sh
   ```
   
   The installer will:
   - Install system dependencies
   - Set up Python virtual environment
   - Install Python packages
   - Prompt for API keys and configuration
   - Create `.env` file
   - Optionally set up systemd services

3. **Follow installer prompts:**
   - Enter Bybit API keys (testnet recommended)
   - Select default profile (conservative recommended)
   - Optionally configure Discord webhook
   - Optionally set up systemd services

4. **Next steps (after installer):**
   - Fetch historical data: `python scripts/fetch_and_check_data.py --symbol BTCUSDT --years 2`
   - Train model: `python train_model.py --symbol BTCUSDT`
   - Run testnet campaign: `python scripts/run_testnet_campaign.py --profile profile_conservative --duration-days 14`
   - Review testnet results before considering live deployment

**Note:** Advanced users can still edit `.env` and `config/config.yaml` manually after installation.

---

## Daily Operations

### Status Check (5 minutes)

**Check Bot Status:**
```bash
# View status file
cat logs/bot_status.json | jq

# Check health status
cat logs/bot_status.json | jq '.health_status'

# Check issues
cat logs/bot_status.json | jq '.issues'

# Check metrics
cat logs/bot_status.json | jq '.metrics'
```

**What to Look For:**
- `health_status`: Should be "HEALTHY"
- `issues`: Should be empty array `[]`
- `warnings`: Review but not critical
- `bot_running`: Should be `true`

**If Issues Found:**
- Review specific issues in status file
- Check logs: `tail -f logs/bot_*.log`
- See "Troubleshooting" section

### Log Review (2 minutes)

**Quick Log Check:**
```bash
# View recent logs
tail -n 50 logs/bot_*.log

# Check for errors
grep -i error logs/bot_*.log | tail -20

# Check for alerts
grep "\[ALERT\]" logs/bot_*.log | tail -20
```

**What to Look For:**
- Errors: Should be minimal
- Alerts: Review any alerts
- Performance guard: Check for status changes
- Trades: Verify trades are executing (if expected)

---

## Weekly Operations

### Performance Review (15 minutes)

**Review Metrics:**
```bash
# Get trade summary (if trade logger supports it)
# Or review logs manually

# Check performance guard status
cat logs/bot_status.json | jq '.metrics.performance_guard_status'

# Review recent trades
grep "Closed position" logs/bot_*.log | tail -20
```

**Metrics to Review:**
- Total PnL (if tracked)
- Win rate
- Number of trades
- Performance guard status
- Current drawdown

**Actions:**
- If performance poor: Consider retraining model
- If performance guard paused: Review and investigate
- If no trades: Check regime filter and signals

### Model Age Check (2 minutes)

**Check Model Age:**
```bash
# Check model file timestamp
ls -lh models/meta_model_*.joblib

# Calculate age
# (Current date - model file date)
```

**If Model Old (> 90 days):**
- Consider retraining
- Or enable auto-retraining

---

## Monthly Operations

### Configuration Review (30 minutes)

**Review Config:**
- Risk settings still appropriate?
- Symbol list still valid?
- Performance guard thresholds still appropriate?
- Regime filter settings still appropriate?

**Adjust if Needed:**
- Only adjust after careful consideration
- Test changes on testnet first
- Document all changes

### Research Harness Run (Optional, 2-4 hours)

**Run Backtest:**
```bash
python research/run_research_suite.py \
  --symbols BTCUSDT ETHUSDT \
  --years 2 \
  --risk-levels conservative moderate
```

**Review Results:**
- Check `docs/PHASE8_RESEARCH_SUMMARY.md`
- Compare to live performance
- Adjust config if research suggests improvements

### Log Archive (5 minutes)

**Archive Old Logs:**
```bash
# Logs auto-rotate, but can manually archive
mkdir -p logs/archive
mv logs/bot_*.log.old logs/archive/  # If needed
```

---

## Incident Response

### Bot Stops Running

**Symptoms:**
- Status file not updating
- No new log entries
- Process not running

**Actions:**
1. Check if process is running: `ps aux | grep live_bot`
2. Check logs for errors: `tail -100 logs/bot_*.log`
3. Check status file: `cat logs/bot_status.json | jq`
4. Restart bot: `python live_bot.py --config config/config.yaml`
5. Monitor for first few minutes

### Performance Guard Paused

**Symptoms:**
- Status shows `performance_guard_status: "PAUSED"`
- Alert received (if enabled)
- No new trades

**Actions:**
1. Review metrics in status file
2. Check recent trades: `grep "Closed position" logs/bot_*.log | tail -20`
3. Review performance guard logs
4. Consider:
   - Retraining model
   - Adjusting thresholds (if too sensitive)
   - Waiting for recovery (auto-recovery enabled)

### Kill Switch Activated

**Symptoms:**
- Bot stopped
- Critical alert (if enabled)
- Log shows "Kill switch triggered"

**Actions:**
1. **DO NOT restart immediately**
2. Review logs: `grep -i "kill switch" logs/bot_*.log`
3. Check account balance and equity
4. Review risk settings
5. Investigate cause:
   - Daily loss limit hit?
   - Max drawdown exceeded?
   - Other risk limit?
6. Adjust config if needed
7. Restart only after investigation

### Health Issues

**Symptoms:**
- Status shows `health_status: "UNHEALTHY"` or `"DEGRADED"`
- Issues listed in status file
- Alerts received (if enabled)

**Actions:**
1. Review issues in status file
2. Check specific issue:
   - **Data feed stalled**: Check WebSocket connection
   - **High API errors**: Check API connectivity, rate limits
   - **No trades**: Check if expected (regime filter, performance guard)
3. Resolve root cause
4. Restart if needed

### API Errors

**Symptoms:**
- High error count in status file
- Errors in logs
- Alerts (if enabled)

**Actions:**
1. Check API key validity
2. Check rate limits
3. Check network connectivity
4. Check exchange status
5. Wait and retry if temporary

---

## Maintenance Tasks

### Model Retraining

**Manual Retraining:**
```bash
# Dry run first
python scripts/scheduled_retrain.py --dry-run

# Actual retrain
python scripts/scheduled_retrain.py --symbols BTCUSDT ETHUSDT
```

**Auto-Retraining:**
- Configured via cron/systemd
- Runs automatically if enabled
- Check logs: `tail -f logs/retrain_*.log`

### Config Updates

**Process:**
1. Backup current config: `cp config/config.yaml config/config.yaml.backup`
2. Edit config: `nano config/config.yaml`
3. Test on testnet first (if major changes)
4. Restart bot: `python live_bot.py`
5. Monitor closely after changes

### Model Updates

**Process:**
1. Train new model: `python train_model.py --symbol BTCUSDT --version 2.1`
2. Test model: Verify files created
3. Update config if version changed
4. Restart bot
5. Monitor performance

---

## Monitoring Commands

### Quick Status
```bash
# Health status
cat logs/bot_status.json | jq '.health_status'

# Performance guard
cat logs/bot_status.json | jq '.metrics.performance_guard_status'

# Open positions
cat logs/bot_status.json | jq '.metrics.open_positions'

# Last trade
cat logs/bot_status.json | jq '.metrics.last_trade_hours_ago'
```

### Log Monitoring
```bash
# Follow logs
tail -f logs/bot_*.log

# Search for specific events
grep "PERFORMANCE_GUARD" logs/bot_*.log
grep "KILL_SWITCH" logs/bot_*.log
grep "Closed position" logs/bot_*.log
```

### Performance Monitoring
```bash
# Check recent trades
grep "Closed position" logs/bot_*.log | tail -20

# Check PnL (if logged)
grep "PnL:" logs/bot_*.log | tail -20
```

---

## Portfolio Layer

### How It Works

The portfolio layer (if enabled) selects a subset of symbols to trade based on cross-sectional ranking.

**Selection Criteria:**
- Recent risk-adjusted return (Sharpe-like)
- Trend strength (ADX)
- Model confidence
- Volatility (lower is better)

**Behavior:**
- Selects top K symbols (default: 3)
- Rebalances periodically (default: daily)
- Limits risk per symbol (default: 10% max)
- Only selected symbols can receive trades

### Configuration

```yaml
portfolio:
  cross_sectional:
    enabled: false  # Set to true to enable
    top_k: 3
    rebalance_interval_minutes: 1440  # 24 hours
    max_symbol_risk_pct: 0.10  # 10%
```

### Monitoring

```bash
# Check portfolio status (if enabled)
# Status is included in bot_status.json when portfolio layer is active
cat logs/bot_status.json | jq '.portfolio_status'
```

### Disabling

If portfolio layer causes issues:
1. Set `portfolio.cross_sectional.enabled: false`
2. Restart bot
3. All symbols become tradable (backward compatible)

---

## Troubleshooting Guide

### Common Issues

**Issue: Bot not receiving candles**
- Check WebSocket connection
- Check symbol names in config
- Check exchange status
- Restart bot

**Issue: No trades executing**
- Check regime filter (may be blocking)
- Check performance guard (may be paused)
- Check confidence threshold (may be too high)
- Check signals in logs

**Issue: High API errors**
- Check API key validity
- Check rate limits
- Check network connectivity
- Reduce request frequency if needed

**Issue: Model predictions seem wrong**
- Check model age (may need retraining)
- Check feature calculation
- Review recent market conditions
- Consider retraining

---

## Best Practices

1. **Start Conservative**: Use conservative settings initially
2. **Monitor Closely**: First week requires close monitoring
3. **Document Changes**: Keep notes on config changes
4. **Test First**: Test changes on testnet before live
5. **Be Patient**: Don't adjust too quickly
6. **Stay Informed**: Monitor market conditions
7. **Regular Reviews**: Weekly performance, monthly config review
8. **Backup Everything**: Config, models, logs

---

## Emergency Contacts

**If Critical Issues:**
1. Stop bot immediately: `Ctrl+C` or kill process
2. Review logs and status
3. Investigate cause
4. Fix issues
5. Test on testnet before restarting

**Support Resources:**
- Documentation: `docs/` directory
- Logs: `logs/` directory
- Status: `logs/bot_status.json`

---

## Checklist Summary

**Daily:**
- [ ] Check status file
- [ ] Review logs for errors
- [ ] Check for alerts

**Weekly:**
- [ ] Review performance metrics
- [ ] Check model age
- [ ] Review open positions

**Monthly:**
- [ ] Review and adjust config
- [ ] Run research harness (optional)
- [ ] Archive old logs

---

## Recommended Profiles (Based on Backtests)

**Note:** These profiles will be refined based on research harness results. Current recommendations are conservative defaults.

### Conservative Profile (Recommended for First Deployment)

**Intended Use:**
- Small account (< $10,000)
- First deployment
- Capital preservation priority

**Key Settings:**
- Leverage: 2x
- Base position: 1%
- Max position: 5%
- Confidence threshold: 0.65
- Ensemble: Enabled
- Regime filter: Strict (ADX 30)

**Representative Metrics (from backtests):**
- Sharpe: [To be populated]
- Profit Factor: [To be populated]
- Max Drawdown: [To be populated]

**Biggest Risks:**
- Low trade count in ranging markets
- May miss opportunities due to strict filters
- Conservative returns

### Moderate Profile (After Validation)

**Intended Use:**
- After successful conservative deployment
- Moderate risk tolerance
- Medium account size ($10,000 - $50,000)

**Key Settings:**
- Leverage: 3x
- Base position: 2%
- Max position: 10%
- Confidence threshold: 0.60
- Ensemble: Enabled
- Regime filter: Moderate (ADX 25)

**Representative Metrics (from backtests):**
- Sharpe: [To be populated]
- Profit Factor: [To be populated]
- Max Drawdown: [To be populated]

**Biggest Risks:**
- Higher drawdowns
- More exposure to volatility
- Moderate leverage risk

### Aggressive Profile (EXPERIMENTAL)

**Intended Use:**
- Only for experienced operators
- High risk tolerance
- Large account size (> $50,000)

**Key Settings:**
- Leverage: 5x
- Base position: 3%
- Max position: 15%
- Confidence threshold: 0.55
- Ensemble: Enabled
- Regime filter: Lenient (ADX 20)

**Representative Metrics (from backtests):**
- Sharpe: [To be populated]
- Profit Factor: [To be populated]
- Max Drawdown: [To be populated]

**Biggest Risks:**
- High drawdowns (up to 20%)
- Leverage risk (5x)
- Potential for large losses
- **WARNING: EXPERIMENTAL - Use with extreme caution**

---

**Version:** 2.1+  
**Last Updated:** December 2025

