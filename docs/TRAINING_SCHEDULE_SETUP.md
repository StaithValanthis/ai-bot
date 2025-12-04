# Training Schedule Setup

**Date**: 2025-12-04  
**Configuration**: Separate schedules for new symbol training vs model rotation

---

## Overview

The bot now has **two separate training schedules**:

1. **Training Queue Processing** (Hourly)
   - Processes new/untrained symbols from the training queue
   - Runs every hour
   - Service: `bybit-bot-train-queue.service` + `bybit-bot-train-queue.timer`

2. **Model Rotation** (Weekly)
   - Retrains existing trained symbols for model rotation
   - Runs weekly on Sunday at 3:00 AM
   - Service: `bybit-bot-retrain.service` + `bybit-bot-retrain.timer`

---

## Services Created

### 1. Training Queue Service (Hourly)

**Service File**: `bybit-bot-train-queue.service`
- **Purpose**: Process training queue for new/untrained symbols
- **Command**: `python scripts/scheduled_retrain.py --skip-retrain`
- **What it does**: Trains symbols in `data/new_symbol_training_queue.json`

**Timer File**: `bybit-bot-train-queue.timer`
- **Schedule**: Every hour at minute 0 (`OnCalendar=*-*-* *:00:00`)
- **Frequency**: Hourly

### 2. Model Rotation Service (Weekly)

**Service File**: `bybit-bot-retrain.service`
- **Purpose**: Retrain existing models for rotation
- **Command**: `python scripts/scheduled_retrain.py --skip-queue`
- **What it does**: Retrains symbols that are already trained (model rotation)

**Timer File**: `bybit-bot-retrain.timer`
- **Schedule**: Weekly on Sunday at 3:00 AM (`OnCalendar=Sun *-*-* 03:00:00`)
- **Frequency**: Weekly

---

## Installation

The `install.sh` script automatically creates and installs both services. If you need to install manually:

```bash
# Copy service files
sudo cp systemd/bybit-bot-train-queue.service /etc/systemd/system/
sudo cp systemd/bybit-bot-train-queue.timer /etc/systemd/system/
sudo cp systemd/bybit-bot-retrain.service /etc/systemd/system/
sudo cp systemd/bybit-bot-retrain.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable timers
sudo systemctl enable bybit-bot-train-queue.timer
sudo systemctl enable bybit-bot-retrain.timer

# Start timers
sudo systemctl start bybit-bot-train-queue.timer
sudo systemctl start bybit-bot-retrain.timer
```

---

## Checking Status

### Training Queue Timer (Hourly)

```bash
# Check timer status
sudo systemctl status bybit-bot-train-queue.timer

# Check when it will run next
sudo systemctl list-timers bybit-bot-train-queue.timer

# View logs from last run
sudo journalctl -u bybit-bot-train-queue.service -n 100

# Manually trigger (for testing)
sudo systemctl start bybit-bot-train-queue.service
```

### Model Rotation Timer (Weekly)

```bash
# Check timer status
sudo systemctl status bybit-bot-retrain.timer

# Check when it will run next
sudo systemctl list-timers bybit-bot-retrain.timer

# View logs from last run
sudo journalctl -u bybit-bot-retrain.service -n 100

# Manually trigger (for testing)
sudo systemctl start bybit-bot-retrain.service
```

---

## Changing Schedules

### Change Training Queue Frequency

Edit `/etc/systemd/system/bybit-bot-train-queue.timer`:

```ini
[Timer]
# Examples:
# Every hour: OnCalendar=*-*-* *:00:00
# Every 30 minutes: OnCalendar=*-*-* *:00,30:00
# Every 2 hours: OnCalendar=*-*-* */2:00:00
OnCalendar=*-*-* *:00:00
```

Then reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart bybit-bot-train-queue.timer
```

### Change Model Rotation Schedule

Edit `/etc/systemd/system/bybit-bot-retrain.timer`:

```ini
[Timer]
# Examples:
# Weekly Sunday 3 AM: OnCalendar=Sun *-*-* 03:00:00
# Daily at 2 AM: OnCalendar=*-*-* 02:00:00
# Monthly on 1st at 3 AM: OnCalendar=*-*-01 03:00:00
OnCalendar=Sun *-*-* 03:00:00
```

Then reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart bybit-bot-retrain.timer
```

---

## How It Works

### Training Queue Processing (Hourly)

1. Bot detects untrained symbols and adds them to `data/new_symbol_training_queue.json`
2. Every hour, `bybit-bot-train-queue.timer` triggers
3. Service runs `scheduled_retrain.py --skip-retrain`
4. Script processes queue, trains new symbols
5. Bot picks up new models on restart

### Model Rotation (Weekly)

1. Every Sunday at 3 AM, `bybit-bot-retrain.timer` triggers
2. Service runs `scheduled_retrain.py --skip-queue`
3. Script checks model age, retrains if needed
4. Evaluates new model, rotates if criteria met
5. Bot uses new model on restart

---

## Summary

- **New/Untrained Symbols**: Trained hourly via `bybit-bot-train-queue.timer`
- **Existing Models**: Rotated weekly via `bybit-bot-retrain.timer`
- **Separation**: Two independent services for different purposes
- **Flexibility**: Each schedule can be changed independently

