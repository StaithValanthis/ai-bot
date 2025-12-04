# Diagnosing Missing Model Files

## Quick Diagnostic Commands

Run these on your server to find where the model files are (or if they exist):

```bash
# 1. Check if models directory exists in repo root
ls -la /home/ubuntu/ai-bot/models/

# 2. Search for model files anywhere in the repo
find /home/ubuntu/ai-bot -name "*.joblib" -type f
find /home/ubuntu/ai-bot -name "model_config*.json" -type f

# 3. Check training logs for errors
tail -100 /home/ubuntu/ai-bot/logs/training_*.log

# 4. Check if models directory exists but is empty
ls -la /home/ubuntu/ai-bot/models/ 2>/dev/null || echo "models/ directory does not exist"

# 5. Check what directory training ran from (check install logs if available)
# Or check the current working directory when training was run
```

## Common Issues

### Issue 1: Training Failed Silently

The install script uses `|| log_warn` which might hide errors. Check training logs:

```bash
# Find training log files
ls -lt /home/ubuntu/ai-bot/logs/training_*.log | head -1

# View the most recent training log
tail -200 $(ls -t /home/ubuntu/ai-bot/logs/training_*.log | head -1)
```

### Issue 2: Models Saved to Wrong Directory

If training ran from a different directory, models might be elsewhere:

```bash
# Search entire home directory
find ~ -name "meta_model_v1.0.joblib" 2>/dev/null
find ~ -name "feature_scaler_v1.0.joblib" 2>/dev/null
```

### Issue 3: Working Directory Mismatch

The systemd service sets `WorkingDirectory=$ABS_SCRIPT_DIR`, but training might have run from elsewhere.

## Solution: Re-run Training

If models are missing or in wrong location, re-run training:

```bash
cd /home/ubuntu/ai-bot
source venv/bin/activate

# Check current directory
pwd  # Should be /home/ubuntu/ai-bot

# Run training (this will save to ./models/ relative to current directory)
python train_model.py --symbol BTCUSDT --days 730

# Verify models were created
ls -lh models/
```

## Fix: Make save_model Use Absolute Paths

The root cause is that `save_model()` uses relative paths. We should fix it to use absolute paths based on project root.

