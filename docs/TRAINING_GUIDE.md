# Training Guide: How to Train Symbols

## Overview

The bot has two types of training:
1. **New Symbol Training**: Training symbols that appear in the universe but haven't been trained yet
2. **Model Retraining**: Retraining existing models with fresh data

## Training Frequency

### Automatic Training: **ENABLED BY DEFAULT**

The bot **automatically trains new symbols** when `scripts/scheduled_retrain.py` runs. Here's how it works:

1. **New Symbol Detection**: When the bot detects untrained symbols, it adds them to a queue file (`data/new_symbol_training_queue.json`)
2. **Automatic Queue Processing**: When `scripts/scheduled_retrain.py` runs (via cron/systemd), it automatically:
   - Processes the training queue (trains all queued symbols)
   - Retrains existing models (if `operations.model_rotation.enabled: true`)
3. **Configuration**: Controlled by `model.auto_train_new_symbols` in config (default: `true`)

**Default Behavior**: 
- `model.auto_train_new_symbols: true` (enabled by default)
- `operations.model_rotation.enabled: false` (retraining disabled by default)
- Queue processing happens automatically when `scheduled_retrain.py` runs

## Manual Training Options

### Option 1: Train Individual Symbols

Train a specific symbol using `train_model.py`:

```bash
# Single symbol training
python train_model.py --symbol BTCUSDT --days 730

# Train multiple symbols (if multi-symbol mode enabled)
python train_model.py --symbol BTCUSDT ETHUSDT SOLUSDT --days 730
```

**What this does:**
- Downloads historical data for the symbol(s)
- Trains a new model
- Saves model with metadata (trained_symbols, training_days, etc.)
- Updates model config

### Option 2: Train All Symbols from Universe

Train all symbols discovered by the universe manager:

```bash
# Uses universe manager to get symbols, then trains all
python train_model.py --days 730
```

**Note**: This respects `model.training_mode`:
- `single_symbol`: Trains only first symbol (backward compatible)
- `multi_symbol`: Trains all symbols with symbol encoding

### Option 3: Process Training Queue

Train all symbols in the queue (new symbols that were detected but not yet trained):

```bash
# Check what's in the queue
cat data/new_symbol_training_queue.json

# Process queue manually (train each symbol)
python -c "
import json
from pathlib import Path
queue_path = Path('data/new_symbol_training_queue.json')
if queue_path.exists():
    with open(queue_path, 'r') as f:
        queue = json.load(f)
    symbols = queue.get('queued_symbols', [])
    print(f'Training {len(symbols)} symbols: {symbols}')
    for symbol in symbols:
        import subprocess
        result = subprocess.run(['python', 'train_model.py', '--symbol', symbol, '--days', '730'])
        if result.returncode == 0:
            print(f'✓ {symbol} trained successfully')
        else:
            print(f'✗ {symbol} training failed')
"

# Or train them one by one manually
python train_model.py --symbol LTCUSDT --days 730
python train_model.py --symbol AVAXUSDT --days 730
# ... etc
```

### Option 4: Use Scheduled Retrain Script (Automatic Training)

The `scheduled_retrain.py` script automatically processes the training queue AND retrains existing models:

```bash
# Dry run (see what would happen)
python scripts/scheduled_retrain.py --dry-run

# Process queue and retrain (automatic)
python scripts/scheduled_retrain.py

# Skip queue processing (only retrain existing models)
python scripts/scheduled_retrain.py --skip-queue

# Retrain specific symbols (skips queue)
python scripts/scheduled_retrain.py --symbols BTCUSDT ETHUSDT --skip-queue
```

**What it does:**
1. **Processes training queue** (if `model.auto_train_new_symbols: true`)
   - Trains all queued symbols
   - Removes successfully trained symbols from queue
2. **Retrains existing models** (if `operations.model_rotation.enabled: true`)
   - Retrains symbols from config or `--symbols` argument

## Setting Up Automatic Training

### Option A: Cron Job (Recommended)

Add to crontab to process queue and retrain weekly:

```bash
# Edit crontab
crontab -e

# Add this line (runs every Sunday at 3 AM)
0 3 * * 0 cd /path/to/ai-bot && /path/to/venv/bin/python scripts/scheduled_retrain.py >> logs/retrain_cron.log 2>&1
```

### Option B: Systemd Timer (If installed via install.sh)

If you set up systemd services during install:

```bash
# Enable and start the retrain timer
sudo systemctl enable bybit-bot-retrain.timer
sudo systemctl start bybit-bot-retrain.timer

# Check status
sudo systemctl status bybit-bot-retrain.timer

# View logs
sudo journalctl -u bybit-bot-retrain.service -f
```

**Note**: The timer runs weekly (Sunday 3 AM) by default.

### Option C: Enable Model Rotation in Config

Edit `config/config.yaml`:

```yaml
operations:
  model_rotation:
    enabled: true  # Enable auto-retraining
    retrain_frequency_days: 30  # Retrain monthly
```

Then run `scheduled_retrain.py` periodically (via cron or systemd).

## Training Queue Management

### View Queue

```bash
cat data/new_symbol_training_queue.json
```

Example output:
```json
{
  "queued_symbols": ["LTCUSDT", "AVAXUSDT", "BNBUSDT"],
  "queued_at": {
    "LTCUSDT": "2025-12-04T03:19:03.423000",
    "AVAXUSDT": "2025-12-04T03:19:03.423000"
  }
}
```

### Clear Queue

```bash
# Clear the queue (after training symbols)
echo '{"queued_symbols": [], "queued_at": {}}' > data/new_symbol_training_queue.json
```

### Add Symbols to Queue Manually

```bash
python -c "
import json
from pathlib import Path
from datetime import datetime

queue_path = Path('data/new_symbol_training_queue.json')
queue = {'queued_symbols': [], 'queued_at': {}}
if queue_path.exists():
    with open(queue_path, 'r') as f:
        queue = json.load(f)

# Add symbols
new_symbols = ['NEWSYMBOLUSDT']
for symbol in new_symbols:
    if symbol not in queue['queued_symbols']:
        queue['queued_symbols'].append(symbol)
        queue['queued_at'][symbol] = datetime.utcnow().isoformat()

with open(queue_path, 'w') as f:
    json.dump(queue, f, indent=2)
print(f'Added {new_symbols} to queue')
"
```

## Training Modes

### Single-Symbol Mode (Default)

```yaml
model:
  training_mode: "single_symbol"
```

- Trains one model per symbol (or one shared model)
- No symbol encoding
- Backward compatible

**Usage:**
```bash
python train_model.py --symbol BTCUSDT
```

### Multi-Symbol Mode

```yaml
model:
  training_mode: "multi_symbol"
  symbol_encoding: "one_hot"  # or "index"
```

- Trains one shared model for all symbols
- Includes symbol encoding (one-hot or index)
- Model learns symbol-specific patterns

**Usage:**
```bash
# Train on all symbols from universe
python train_model.py
```

## Quick Reference

### Check Model Coverage

```bash
python scripts/check_model_coverage.py
```

### Train New Symbols (from queue)

```bash
# View queue
cat data/new_symbol_training_queue.json | jq '.queued_symbols'

# Train each symbol
for symbol in $(cat data/new_symbol_training_queue.json | jq -r '.queued_symbols[]'); do
    echo "Training $symbol..."
    python train_model.py --symbol $symbol --days 730
done
```

### Retrain Existing Models

```bash
# Enable rotation in config first
# Then run:
python scripts/scheduled_retrain.py --symbols BTCUSDT ETHUSDT
```

## Troubleshooting

### "Symbol is blocked" Error

If a symbol is blocked, check:
1. Is it trained? Run `python scripts/check_model_coverage.py`
2. Does it have enough history? (needs >= 90 days by default)
3. Is data coverage sufficient? (needs >= 95% by default)

### Training Fails

Check logs:
```bash
tail -f logs/training_*.log
```

Common issues:
- Insufficient data: Symbol needs more history
- API errors: Check API keys and network
- Memory issues: Reduce number of symbols or days

### Model Not Found After Training

Check model files:
```bash
ls -lh models/
```

Models should be saved to `models/` directory with absolute paths.

