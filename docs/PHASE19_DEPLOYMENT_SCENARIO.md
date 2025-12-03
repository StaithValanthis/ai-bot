# Phase 19: Realistic "Hands-Off" Deployment Scenario

## Overview

This document describes a realistic deployment scenario where the bot runs with minimal human intervention, including configuration, automation setup, and expected behavior.

---

## Deployment Environment

### Infrastructure

**Server:**
- Linux (Ubuntu 20.04+ recommended)
- Python 3.8+
- 4GB+ RAM
- 10GB+ disk space
- Stable internet connection
- NTP time synchronization

**Example Setup:**
```bash
# Ubuntu server
sudo apt update
sudo apt install python3.8 python3-pip ntp
sudo systemctl enable ntp
```

---

## Configuration

### Recommended Initial Config

**File:** `config/config.yaml`

```yaml
# Exchange Settings
exchange:
  name: "bybit"
  testnet: false  # Set to true for initial testing
  api_key: "${BYBIT_API_KEY}"
  api_secret: "${BYBIT_API_SECRET}"

# Trading Settings
trading:
  symbols:
    - "BTCUSDT"
    - "ETHUSDT"
  timeframe: "1h"

# Model Settings
model:
  version: "2.1"
  confidence_threshold: 0.65  # Higher for conservative
  use_ensemble: true
  ensemble_xgb_weight: 0.7

# Risk Management (Conservative)
risk:
  max_leverage: 2.0
  max_position_size: 0.05  # 5%
  base_position_size: 0.01  # 1%
  max_daily_loss: 0.03  # 3%
  max_drawdown: 0.10  # 10%
  max_open_positions: 2
  stop_loss_pct: 0.02  # 2%
  take_profit_pct: 0.03  # 3%

# Regime Filter
regime_filter:
  enabled: true
  adx_threshold: 25
  volatility_threshold: 2.0
  allow_ranging: false

# Performance Guard
performance_guard:
  enabled: true
  rolling_window_trades: 10
  win_rate_threshold_reduced: 0.40
  win_rate_threshold_paused: 0.30
  drawdown_threshold_reduced: 0.05
  drawdown_threshold_paused: 0.10
  recovery_win_rate: 0.45
  recovery_drawdown: 0.05

# Portfolio Selection (Optional)
portfolio:
  cross_sectional:
    enabled: false  # Start disabled, enable after validation
    top_k: 3
    rebalance_interval_minutes: 1440
    max_symbol_risk_pct: 0.10

# Operations
operations:
  health_check_interval_seconds: 300  # 5 minutes
  status_file_path: "logs/bot_status.json"
  
  model_rotation:
    enabled: true  # Enable after initial validation
    retrain_frequency_days: 30
    min_sharpe_ratio: 1.0
    min_profit_factor: 1.2
    max_drawdown_threshold: 0.20
    min_trades: 50
  
  alerts:
    enabled: true  # Enable if using Discord
    discord_webhook_url: "${DISCORD_WEBHOOK_URL}"  # Optional
    alert_on_pause: true
    alert_on_kill_switch: true
    alert_on_health_issues: true
```

---

## Automation Setup

### 1. Live Bot (systemd)

**File:** `/etc/systemd/system/bybit-bot.service`

```ini
[Unit]
Description=Bybit AI Trading Bot
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/home/trader/ai-bot
Environment="PATH=/home/trader/ai-bot/venv/bin"
ExecStart=/home/trader/ai-bot/venv/bin/python live_bot.py --config config/config.yaml
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Commands:**
```bash
# Enable and start
sudo systemctl enable bybit-bot
sudo systemctl start bybit-bot

# Check status
sudo systemctl status bybit-bot

# View logs
sudo journalctl -u bybit-bot -f
```

### 2. Auto-Retraining (cron)

**Cron Entry:**
```bash
# Run daily at 2 AM
0 2 * * * cd /home/trader/ai-bot && /home/trader/ai-bot/venv/bin/python scripts/scheduled_retrain.py >> logs/retrain_cron.log 2>&1
```

**Setup:**
```bash
# Edit crontab
crontab -e

# Add entry above
```

---

## Expected Behavior

### Normal Operation

**Daily:**
- Bot runs continuously
- Processes candles every hour
- Generates signals and executes trades (if conditions met)
- Health checks every 5 minutes
- Status file updated every 5 minutes

**Weekly:**
- Auto-retraining runs (if enabled, default: monthly)
- Model rotation occurs if new model meets criteria
- Logs rotate automatically

**Monthly:**
- Model retraining (if enabled)
- Performance review (manual or automated)

### Performance Guard Behavior

**Normal State:**
- Full trading
- Normal position sizes
- Normal confidence threshold

**Reduced Risk State:**
- Triggered by: Win rate < 40% OR losing streak >= 5 OR drawdown > 5%
- Actions:
  - Position size reduced to 50%
  - Confidence threshold increased by 0.1
  - Alert sent (if enabled)

**Paused State:**
- Triggered by: Win rate < 30% OR losing streak >= 10 OR drawdown > 10%
- Actions:
  - Trading stopped
  - Alert sent (if enabled)
  - Auto-recovery when conditions improve

**Recovery:**
- Triggered by: Win rate >= 45% AND drawdown < 5% AND >= 5 trades
- Actions:
  - Status returns to NORMAL
  - Full trading resumes
  - Alert sent (if enabled)

### Regime Filter Behavior

**Trending Markets (ADX > 25):**
- Trading allowed
- Full position size
- Direction matching enforced (LONG in uptrend, SHORT in downtrend)

**Ranging Markets (ADX < 25):**
- Trading blocked (if `allow_ranging: false`)
- No new positions
- Existing positions can be closed

**High Volatility:**
- Trading allowed but with reduced size (50% multiplier)
- Risk management still active

### Health Monitoring

**Status File Updates:**
- Every 5 minutes
- Location: `logs/bot_status.json`
- Contains: Health status, metrics, issues, warnings

**Health Status Levels:**
- **HEALTHY**: All systems normal
- **DEGRADED**: Minor issues (warnings)
- **UNHEALTHY**: Critical issues (data feed stalled, high API errors)

**Alerts Triggered:**
- Health status = UNHEALTHY
- Performance guard PAUSED
- Kill switch activated
- Model rotation (if enabled)

---

## Safety Nets

### 1. Performance Guard

**Purpose:** Auto-throttle risk during poor performance

**Thresholds:**
- Reduced: Win rate < 40%, drawdown > 5%, losing streak >= 5
- Paused: Win rate < 30%, drawdown > 10%, losing streak >= 10

**Actions:**
- Reduced: 50% position size, +0.1 confidence threshold
- Paused: Stop trading, wait for recovery

**Recovery:**
- Win rate >= 45%, drawdown < 5%, >= 5 trades

**Status:** ✅ **ACTIVE** - Prevents death spirals

---

### 2. Kill Switch

**Purpose:** Emergency shutdown

**Conditions:**
- Daily loss limit exceeded
- Max drawdown exceeded
- Other critical risk limits

**Actions:**
- Bot stops immediately
- Critical alert sent
- Requires manual intervention to restart

**Status:** ✅ **ACTIVE** - Final safety net

---

### 3. Health Checks

**Purpose:** Monitor bot health and detect issues

**Checks:**
- Data feed status (no candles for > 15 minutes)
- API error rate (> 5 errors in 10 minutes)
- Trading activity (no trades for > 7 days)

**Actions:**
- Status file updated
- Alerts sent (if enabled)
- Issues logged

**Status:** ✅ **ACTIVE** - Continuous monitoring

---

### 4. Model Rotation

**Purpose:** Keep models fresh and prevent degradation

**Process:**
1. Retrain on latest data (monthly)
2. Evaluate new model
3. Check promotion criteria:
   - Sharpe > 1.0
   - Profit factor > 1.2
   - Max drawdown < 20%
   - Trade count >= 50
4. Rotate if criteria met, otherwise keep current

**Safety:**
- Old models archived (can rollback)
- Dry-run mode available
- Strict promotion criteria

**Status:** ✅ **ACTIVE** (if enabled) - Prevents model degradation

---

## What This System CANNOT Guarantee

### 1. Profitability
- **Cannot guarantee**: Positive returns
- **Cannot guarantee**: Beating buy-and-hold
- **Cannot guarantee**: Consistent monthly profits

**Reality:**
- Trading involves risk
- Losses are possible
- Past performance ≠ future results

### 2. Market Conditions
- **Cannot prevent**: Losses in extreme events (flash crashes, exchange issues)
- **Cannot prevent**: Losses during regime breaks (sudden structural changes)
- **Cannot prevent**: Losses in prolonged ranging markets

**Mitigation:**
- Performance guard throttles during poor performance
- Regime filter avoids unfavorable conditions
- Kill switch prevents catastrophic losses

### 3. Technical Failures
- **Cannot prevent**: Exchange API failures
- **Cannot prevent**: Network outages
- **Cannot prevent**: Data feed interruptions

**Mitigation:**
- Health checks detect issues
- Alerts notify operator
- Bot can resume after issues resolved

### 4. Model Degradation
- **Cannot prevent**: Model performance degradation over time
- **Cannot prevent**: Overfitting to historical data
- **Cannot prevent**: Regime shifts that invalidate model

**Mitigation:**
- Auto-retraining updates models
- Ensemble reduces overfitting
- Performance guard detects degradation

### 5. Human Error
- **Cannot prevent**: Configuration errors
- **Cannot prevent**: API key issues
- **Cannot prevent**: Incorrect risk settings

**Mitigation:**
- Comprehensive documentation
- Production readiness checklist
- Conservative defaults

---

## Minimal Operator Responsibilities

### Daily (Optional)
- Check status file: `cat logs/bot_status.json | jq`
- Review logs for errors: `tail -f logs/bot_*.log`
- Check for alerts (if Discord enabled)

### Weekly (Recommended)
- Review performance metrics
- Check health status
- Review any alerts

### Monthly (Recommended)
- Review model age (if auto-retraining disabled)
- Review and adjust config if needed
- Run research harness (optional)

### As Needed
- Respond to critical alerts
- Investigate health issues
- Adjust config if market conditions change significantly

---

## Example Timeline

### Week 1: Initial Deployment
- **Day 1**: Deploy with conservative settings, monitor closely
- **Days 2-7**: Monitor daily, verify all components working
- **End of Week**: Review performance, adjust if needed

### Weeks 2-4: Validation
- **Daily**: Quick status check (optional)
- **Weekly**: Performance review
- **End of Month**: Full review, consider enabling auto-retraining

### Month 2+: Hands-Off Operation
- **Daily**: Automated (health checks, trading)
- **Weekly**: Quick review (optional)
- **Monthly**: Performance review, config adjustment if needed
- **Quarterly**: Full system review

---

## Monitoring Dashboard (Optional)

### Simple Status Check Script

**File:** `scripts/check_status.sh`

```bash
#!/bin/bash
# Quick status check

echo "=== Bot Status ==="
cat logs/bot_status.json | jq '.health_status, .metrics.performance_guard_status, .metrics.open_positions'

echo ""
echo "=== Recent Alerts ==="
grep "\[ALERT\]" logs/bot_*.log | tail -5

echo ""
echo "=== Recent Trades ==="
grep "Closed position" logs/bot_*.log | tail -5
```

**Usage:**
```bash
chmod +x scripts/check_status.sh
./scripts/check_status.sh
```

---

## Troubleshooting

### Bot Not Trading

**Check:**
1. Performance guard status (may be PAUSED)
2. Regime filter (may be blocking)
3. Confidence threshold (may be too high)
4. Portfolio selector (if enabled, symbol may not be selected)

**Actions:**
- Review status file
- Check logs for specific reasons
- Adjust config if needed

### Performance Guard Paused

**Check:**
1. Recent win rate
2. Current drawdown
3. Losing streak

**Actions:**
- Review metrics in status file
- Consider retraining model
- Wait for auto-recovery (if conditions improve)

### Health Issues

**Check:**
1. Data feed status
2. API error count
3. Last trade timestamp

**Actions:**
- Check exchange status
- Verify API keys
- Check network connectivity
- Restart if needed

---

## Summary

**Deployment Model:** ✅ **HANDS-OFF** (with monitoring)

**Automation:**
- ✅ Trading (fully automated)
- ✅ Risk management (fully automated)
- ✅ Health monitoring (fully automated)
- ✅ Model retraining (optional, automated)
- ✅ Alerts (optional, automated)

**Operator Responsibilities:**
- ⚠️ Minimal: Weekly review, monthly config check
- ⚠️ As needed: Respond to alerts, investigate issues

**Safety Nets:**
- ✅ Performance guard (auto-throttling)
- ✅ Kill switch (emergency shutdown)
- ✅ Health checks (issue detection)
- ✅ Model rotation (prevent degradation)

**Limitations:**
- ⚠️ Cannot guarantee profitability
- ⚠️ Cannot prevent all losses
- ⚠️ Depends on exchange API stability
- ⚠️ Subject to market regime changes

---

**Date:** December 2025  
**Status:** Production Deployment Guide

