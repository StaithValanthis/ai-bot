# Phase 10: Self-Management & Operational Automation

## Overview

This document describes the operations layer for automated retraining, model rotation, health checks, and alerting to make the bot as close to "turn on and leave it alone" as safely practical.

---

## Components

### 1. Auto-Retraining & Model Rotation

**Script:** `scripts/scheduled_retrain.py`

**Purpose:**
- Periodically retrain models on latest data
- Evaluate new models against promotion criteria
- Rotate models only if new model meets quality thresholds
- Maintain audit trail of all decisions

**Workflow:**
1. **Data Collection**: Pull latest historical data (e.g., last 730 days)
2. **Model Training**: Train new model using v2.1 pipeline (with ensemble)
3. **Evaluation**: Run lightweight backtest or use research harness
4. **Promotion Criteria Check**:
   - Sharpe ratio > threshold (e.g., 1.0)
   - Profit factor > threshold (e.g., 1.2)
   - Max drawdown < threshold (e.g., 20%)
   - Minimum trade count (e.g., 50 trades)
   - Outperforms current production model
5. **Model Rotation**: If criteria met, promote new model; otherwise keep current
6. **Logging**: Log all decisions and metrics

**Promotion Criteria (Configurable):**
```yaml
model_rotation:
  enabled: true
  retrain_frequency_days: 30  # Retrain monthly
  min_sharpe_ratio: 1.0
  min_profit_factor: 1.2
  max_drawdown_threshold: 0.20
  min_trades: 50
  require_outperformance: true  # Must beat current model
```

**Implementation Status:** ⚠️ Framework designed, needs implementation

---

### 2. Performance Guard Integration

**Location:** `src/risk/performance_guard.py`

**Current Capabilities:**
- ✅ Monitors rolling win rate, drawdown, losing streaks
- ✅ Auto-throttles (REDUCED) or pauses (PAUSED) trading
- ✅ Auto-recovers when performance improves

**Enhancements Needed:**
- **Trigger Re-Train**: If performance degrades significantly, trigger model re-evaluation
- **Model Quality Check**: Compare live performance to backtest expectations
- **Alert on Degradation**: Log critical alerts when performance guard activates

**Integration Points:**
- `live_bot.py`: Already integrated ✅
- `scripts/scheduled_retrain.py`: Should check performance guard status

**Implementation Status:** ✅ Core functionality implemented, enhancements pending

---

### 3. Health Checks & Alerts

**Module:** `src/monitoring/health.py` (to be created)

**Purpose:**
- Periodic health checks
- Heartbeat logging
- Status file generation
- Alert hooks (Discord/email ready)

**Health Check Components:**

1. **Bot Status**:
   - Is bot running?
   - Last candle received timestamp
   - WebSocket connection status
   - API connection status

2. **Trading Status**:
   - Performance guard status (NORMAL/REDUCED/PAUSED)
   - Regime filter status (current regime)
   - Open positions count
   - Recent trade count

3. **Model Status**:
   - Model version in use
   - Model age (days since training)
   - Last retrain date
   - Model performance metrics (if available)

4. **Risk Status**:
   - Current drawdown
   - Daily PnL
   - Position sizes
   - Leverage usage

**Status File:**
- Location: `logs/bot_status.json`
- Updated every 5 minutes
- Contains all health check data

**Alert Conditions:**
- Performance guard PAUSED
- Kill switch activated
- Model age > threshold (e.g., 90 days)
- Drawdown > critical threshold
- API connection lost > 5 minutes
- No trades in 7 days (if expected)

**Implementation Status:** ⚠️ Design complete, needs implementation

---

### 4. Automated Monitoring

**Logging:**
- ✅ All components use structured logging (loguru)
- ✅ Trade logger tracks all activities
- ✅ Performance guard logs status changes

**Monitoring Points:**
1. **Kill Switch Activations**: Logged with CRITICAL level
2. **Regime Filter Changes**: Logged when regime changes
3. **Performance Guard Actions**: Logged when status changes
4. **Model Rotations**: Logged with full metrics
5. **API Errors**: Logged with ERROR level

**Alert Hooks:**
- Function: `src/monitoring/alerts.py::send_alert()`
- Can be wired to:
  - Discord webhook
  - Email (SMTP)
  - Slack webhook
  - Custom webhook

**Implementation Status:** ⚠️ Alert framework designed, needs implementation

---

## Implementation Plan

### Priority 1: Health Checks (Week 1)
- Create `src/monitoring/health.py`
- Implement health check function
- Create status file writer
- Integrate into `live_bot.py` (periodic checks)

### Priority 2: Auto-Retraining (Week 2)
- Create `scripts/scheduled_retrain.py`
- Implement promotion criteria
- Add model rotation logic
- Test with dry-run mode

### Priority 3: Alerting (Week 3)
- Create `src/monitoring/alerts.py`
- Implement alert hooks
- Add Discord/email examples
- Test alert delivery

---

## Configuration

### Recommended Defaults

```yaml
# Operations & Automation
operations:
  health_check_interval_seconds: 300  # 5 minutes
  status_file_path: "logs/bot_status.json"
  
  model_rotation:
    enabled: true
    retrain_frequency_days: 30
    min_sharpe_ratio: 1.0
    min_profit_factor: 1.2
    max_drawdown_threshold: 0.20
    min_trades: 50
    require_outperformance: true
  
  alerts:
    enabled: true
    discord_webhook_url: ""  # Optional
    email_smtp_server: ""  # Optional
    email_recipients: []  # Optional
    alert_on_pause: true
    alert_on_kill_switch: true
    alert_on_model_rotation: true
```

---

## Operational Workflow

### Daily Operations (Automated)
1. Health checks run every 5 minutes
2. Status file updated
3. Performance guard monitors continuously
4. Regime filter updates on each candle

### Weekly Operations (Automated)
1. Model performance review (if enabled)
2. Log rotation (if configured)

### Monthly Operations (Automated)
1. Model retraining (if enabled)
2. Model rotation (if criteria met)
3. Performance report generation

### Manual Operations (Minimal)
1. Monitor logs (optional)
2. Review status file (optional)
3. Adjust config if needed (rare)

---

## Safety Features

1. **Dry-Run Mode**: Test retraining without rotating models
2. **Rollback Capability**: Keep previous model version
3. **Promotion Gating**: Strict criteria prevent bad models
4. **Alerting**: Critical events trigger alerts
5. **Kill Switch**: Manual override always available

---

## Testing Recommendations

1. **Health Checks**: Test all health check components
2. **Retraining**: Test retraining pipeline on testnet
3. **Model Rotation**: Test promotion criteria
4. **Alerts**: Test alert delivery
5. **Recovery**: Test recovery from failures

---

## Status

**Current State:**
- ✅ Performance guard integrated and working
- ✅ Regime filter integrated and working
- ⚠️ Health checks: Design complete, needs implementation
- ⚠️ Auto-retraining: Design complete, needs implementation
- ⚠️ Alerting: Design complete, needs implementation

**Next Steps:**
1. Implement health check module
2. Implement auto-retraining script
3. Implement alert framework
4. Test end-to-end automation
5. Document operational procedures

---

**Date:** December 2025  
**Status:** Design Complete, Implementation Pending

