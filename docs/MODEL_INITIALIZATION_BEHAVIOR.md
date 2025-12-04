# Model Initialization Behavior (Current State)

This document describes how models are currently loaded and when training occurs, **before** the model discovery system is implemented.

## Current Model Loading (live_bot.py)

### Entry Point
- `TradingBot.__init__()` calls `get_model_paths(self.config)`
- Uses `MetaPredictor` to load model, scaler, and config

### Path Resolution
- `get_model_paths()` in `src/config/config_loader.py`:
  - Reads `config['model']['path']`, `config['model']['scaler_path']`, `config['model']['config_path']`
  - Defaults to `models/meta_model_v1.0.*` if not specified
  - **No discovery** - uses hard-coded paths from config

### Model Loading
- `MetaPredictor.__init__()`:
  - Loads model from `model_path` (joblib)
  - Loads scaler from `scaler_path` (joblib)
  - Loads metadata from `config_path` (JSON)
  - **Fails if files don't exist** - no fallback or discovery

### Current Limitations
- ❌ No scanning of `models/` directory
- ❌ No version selection logic
- ❌ Hard-coded to version "1.0" in config.yaml
- ❌ No check for alternative/compatible models

## Current Training Flow (train_model.py)

### Entry Point
- CLI script: `python train_model.py [--symbol SYMBOL] [--days DAYS] [--version VERSION]`
- Called from:
  - Manual execution
  - `install.sh` (first-time setup)
  - Background training threads in `live_bot.py`

### Current Behavior
- **No check for existing models** before training
- Always trains if called (unless data is missing)
- Uses `--version` argument or defaults to config `model.version` (usually "1.0")
- Saves to `models/meta_model_v{version}.joblib` (overwrites if exists)

### Training Triggers
1. **Manual**: User runs `python train_model.py`
2. **Install**: `install.sh` prompts and runs training
3. **Auto-training**: `live_bot.py` background threads train new symbols
4. **Scheduled**: `scripts/scheduled_retrain.py` (if enabled)

### Current Limitations
- ❌ No check if compatible model already exists
- ❌ No `--force-train` flag to override
- ❌ Always overwrites existing model files
- ❌ No discovery of existing models before training

## Scheduled Retraining (scripts/scheduled_retrain.py)

### Current Behavior
- `ModelRotationManager.should_retrain()`:
  - Checks model file modification time
  - Compares to `retrain_frequency_days` config
  - **Does not check model compatibility** - only age
  - Uses config-based paths (no discovery)

### Limitations
- ❌ Only checks file age, not compatibility
- ❌ No discovery of alternative models
- ❌ Assumes single model per symbol (legacy behavior)

## Installer Behavior (install.sh)

### Current Behavior
- Prompts: "Do you want to train the model now?"
- If yes, runs: `python train_model.py --symbol ... --days ...`
- **No check for existing models** before prompting
- Always trains if user says yes

### Limitations
- ❌ No discovery of existing models
- ❌ No option to reuse existing model
- ❌ May retrain unnecessarily

## Summary

**Current State:**
- Models are loaded from **hard-coded config paths** (version "1.0")
- Training **always runs** if called (no existence check)
- No **model discovery** or **version selection**
- No **compatibility checking** before training

**What's Missing:**
- Model discovery (scan `models/` directory)
- Compatibility checking (training_mode, symbol_encoding, etc.)
- Smart selection (best matching model)
- Training skip logic (reuse existing compatible model)

