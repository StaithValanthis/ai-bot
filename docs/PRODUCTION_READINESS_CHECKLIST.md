# Production Readiness Checklist

## Overview

This checklist ensures the v2.1 bot is ready for production deployment. Complete all items before live trading.

---

## Infrastructure Prerequisites

### System Requirements
- [ ] **Operating System**: Linux (Ubuntu 20.04+ recommended) or macOS/Windows for testing
- [ ] **Python Version**: Python 3.8 or higher
- [ ] **System Time**: Synchronized with NTP (critical for accurate timestamps)
- [ ] **Disk Space**: Minimum 10GB free (for data, models, logs)
- [ ] **Network**: Stable internet connection with low latency to exchange
- [ ] **Memory**: Minimum 4GB RAM (8GB+ recommended)

### Python Environment
- [ ] **Virtual Environment**: Created and activated
- [ ] **Dependencies**: All packages installed (`pip install -r requirements.txt`)
- [ ] **Python Path**: Correctly configured

---

## One-Time Setup

### API Configuration
- [ ] **Bybit API Keys**: Generated and secured
- [ ] **Environment Variables**: `.env` file created with:
  - `BYBIT_API_KEY`
  - `BYBIT_API_SECRET`
- [ ] **Testnet Testing**: Verified API keys work on testnet
- [ ] **API Permissions**: Keys have trading permissions (not just read)

### Configuration
- [ ] **Config File**: `config/config.yaml` reviewed and adjusted
- [ ] **Risk Settings**: Conservative settings for initial deployment
- [ ] **Symbols**: Selected (start with BTCUSDT, ETHUSDT)
- [ ] **Testnet Mode**: Enabled for initial testing (`testnet: true`)

### Model Training
- [ ] **Initial Training**: Model trained on historical data
- [ ] **Model Validation**: Walk-forward validation completed
- [ ] **Model Files**: Present in `models/` directory:
  - `meta_model_v*.joblib`
  - `feature_scaler_v*.joblib`
  - `model_config_v*.json`
- [ ] **Model Version**: Matches config file

---

## Pre-Deployment Testing

### Testnet Validation
- [ ] **Testnet Deployment**: Bot run on testnet for minimum 2 weeks
- [ ] **Signal Generation**: Verified signals are generated correctly
- [ ] **Order Execution**: Verified orders are placed correctly
- [ ] **Risk Controls**: Verified stop-loss, take-profit work
- [ ] **Performance Guard**: Verified throttling works
- [ ] **Regime Filter**: Verified regime classification works
- [ ] **Health Checks**: Verified status file updates
- [ ] **Alerts**: Tested (if enabled)

### Component Verification
- [ ] **Data Feed**: WebSocket connection stable
- [ ] **Feature Calculation**: Indicators calculated correctly
- [ ] **Model Prediction**: Confidence scores reasonable
- [ ] **Position Sizing**: Sizes calculated correctly
- [ ] **Risk Limits**: Enforced correctly
- [ ] **Logging**: Logs written correctly

---

## Risk Controls Verification

### Position Sizing
- [ ] **Base Size**: Verified (recommended: 1-2% for conservative)
- [ ] **Max Size**: Verified (recommended: 5-10% for conservative)
- [ ] **Volatility Targeting**: Enabled and working
- [ ] **Confidence Scaling**: Working correctly

### Risk Limits
- [ ] **Max Leverage**: Set appropriately (recommended: 2-3x for conservative)
- [ ] **Daily Loss Limit**: Set (recommended: 3-5% for conservative)
- [ ] **Max Drawdown**: Set (recommended: 10-15% for conservative)
- [ ] **Max Open Positions**: Set (recommended: 2-3 for conservative)
- [ ] **Stop Loss**: Set (recommended: 2%)
- [ ] **Take Profit**: Set (recommended: 3%)

### Safety Features
- [ ] **Performance Guard**: Enabled and thresholds set
- [ ] **Regime Filter**: Enabled and configured
- [ ] **Kill Switch**: Tested and verified
- [ ] **Health Monitoring**: Enabled

---

## Monitoring & Operations

### Logging
- [ ] **Log Directory**: `logs/` exists and writable
- [ ] **Log Rotation**: Configured (automatic with loguru)
- [ ] **Log Levels**: Set appropriately (INFO for production)

### Health Monitoring
- [ ] **Status File**: Location known (`logs/bot_status.json`)
- [ ] **Health Checks**: Running automatically
- [ ] **Status Monitoring**: Know how to check status

### Alerts (Optional)
- [ ] **Alerts Enabled**: If using, configured in config
- [ ] **Discord Webhook**: Tested (if using)
- [ ] **Email**: Configured (if using)
- [ ] **Alert Testing**: Verified alerts are received

### Automation
- [ ] **Auto-Retraining**: Configured (if enabled)
- [ ] **Cron/Scheduler**: Set up for retraining (if enabled)
- [ ] **Model Backup**: Strategy for backing up models

---

## Documentation Review

### Key Documents Read
- [ ] **README.md**: Read and understood
- [ ] **QUICK_START.md**: Followed setup instructions
- [ ] **PHASE11_VALIDATION_AND_DEFAULTS.md**: Reviewed recommended settings
- [ ] **PHASE12_OPERATIONS_IMPLEMENTATION.md**: Understood operations
- [ ] **PRODUCTION_READINESS_CHECKLIST.md**: This document

### Understanding
- [ ] **Strategy**: Understand meta-labeling on trend-following
- [ ] **Risk Management**: Understand all risk controls
- [ ] **Operations**: Understand how bot runs and monitors itself
- [ ] **Limitations**: Understand risks and limitations

---

## Final Checks

### Before Going Live
- [ ] **Testnet Validation**: Minimum 2 weeks successful
- [ ] **Config Review**: All settings appropriate for live trading
- [ ] **Testnet Disabled**: `testnet: false` in config (when ready)
- [ ] **Small Capital**: Start with small amount (recommended)
- [ ] **Monitoring Plan**: Know how to monitor bot
- [ ] **Emergency Procedures**: Know how to stop bot if needed

### Deployment
- [ ] **Backup**: Config and model files backed up
- [ ] **Documentation**: All notes and configs documented
- [ ] **Access**: Know how to access logs and status
- [ ] **Support**: Know where to get help if needed

---

## Post-Deployment Monitoring

### First Week
- [ ] **Daily Checks**: Check status file daily
- [ ] **Log Review**: Review logs for errors
- [ ] **Performance**: Monitor PnL and metrics
- [ ] **Alerts**: Respond to any alerts promptly

### Ongoing
- [ ] **Weekly Review**: Review performance weekly
- [ ] **Monthly Review**: Review and adjust config if needed
- [ ] **Model Updates**: Retrain models periodically (if auto-retraining disabled)
- [ ] **Research Harness**: Run periodically to validate strategy

---

## Emergency Procedures

### If Bot Stops
1. Check logs: `tail -f logs/bot_*.log`
2. Check status: `cat logs/bot_status.json | jq`
3. Restart if needed: `python live_bot.py`

### If Performance Guard Pauses Trading
1. Review metrics in status file
2. Check recent trades
3. Consider retraining model
4. Adjust config if needed

### If Kill Switch Activates
1. **DO NOT** restart immediately
2. Review logs and status
3. Investigate cause
4. Adjust risk settings if needed
5. Restart only after investigation

### If Health Issues Detected
1. Check status file for specific issues
2. Review logs for errors
3. Check API connectivity
4. Check data feed status
5. Resolve issues before restarting

---

## Recommended Initial Settings

### Conservative (Recommended for First Deployment)
```yaml
risk:
  max_leverage: 2.0
  max_position_size: 0.05  # 5%
  base_position_size: 0.01  # 1%
  max_daily_loss: 0.03  # 3%
  max_drawdown: 0.10  # 10%
  max_open_positions: 2

model:
  confidence_threshold: 0.65  # Higher threshold

performance_guard:
  enabled: true
  # Default thresholds are conservative
```

---

## Sign-Off

**Before going live, confirm:**
- [ ] All checklist items completed
- [ ] Testnet validation successful (2+ weeks)
- [ ] Risk settings appropriate
- [ ] Monitoring in place
- [ ] Emergency procedures understood
- [ ] Ready to accept risk of trading

**Date:** _______________  
**Name:** _______________  
**Signature:** _______________

---

## Notes

- **Start Small**: Begin with small capital
- **Monitor Closely**: First week requires close monitoring
- **Be Patient**: Don't adjust too quickly
- **Stay Informed**: Monitor market conditions
- **Document Changes**: Keep notes on any config changes

---

**Remember:** Trading involves risk. No guarantees of profit. Use at your own risk.

---

**Version:** 2.1  
**Last Updated:** December 2025

