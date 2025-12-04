# Model Discovery and Selection

This document describes how the bot discovers available trained models and selects the best one for the current configuration.

## Overview

The model discovery system (`src/models/model_registry.py`) scans the `models/` directory for trained model artifacts and selects the best matching model based on configuration requirements.

## Model Discovery

### What Gets Discovered

The system scans for:
- `meta_model_v*.joblib` - Trained model files
- `feature_scaler_v*.joblib` - Feature scaler files
- `model_config_v*.json` - Model metadata/config files

Models are grouped by version (extracted from filename pattern `vX.Y`).

### Discovery Process

1. **Scan Directory**: `list_available_models()` scans `models/` directory
2. **Group by Version**: Groups model/scaler/config files by version number
3. **Load Metadata**: Reads `model_config_v*.json` to get training metadata
4. **Validate Completeness**: Checks that all three files exist for each version
5. **Return List**: Returns list of model dictionaries with metadata

### Model Dictionary Structure

Each model dictionary contains:
```python
{
    'version': '1.0',  # Version string
    'model_path': Path(...),  # Path to model file
    'scaler_path': Path(...),  # Path to scaler file
    'config_path': Path(...),  # Path to config file
    'exists': True,  # Whether all files exist
    'metadata': {  # From model_config_v*.json
        'training_mode': 'single_symbol' | 'multi_symbol',
        'symbol_encoding_type': 'one_hot' | 'index',
        'trained_symbols': ['BTCUSDT', 'ETHUSDT', ...],
        'training_days': 730,
        'training_end_timestamp': '2025-12-04T12:00:00',
        'performance': {...},
        ...
    }
}
```

## Model Selection

### Selection Criteria

`select_best_model(config)` applies these criteria in order:

1. **File Completeness**: Model must have all three files (model, scaler, config)
2. **Training Mode Match**: `training_mode` must match config requirement
   - Config: `model.training_mode` (default: `'single_symbol'`)
   - Model: `metadata.training_mode`
3. **Symbol Encoding Match**: For `multi_symbol` mode, `symbol_encoding_type` must match
   - Config: `model.symbol_encoding` (default: `'one_hot'`)
   - Model: `metadata.symbol_encoding_type`
4. **Scoring**: Among compatible models, score based on:
   - **Symbol Coverage**: +10 points per trained symbol
   - **Recency**: Up to 365 points for recent training (more recent = higher score)
   - **Version**: Higher version number = higher score (major * 100 + minor)
5. **Tie-Breaking**: Highest score wins; if tied, prefer higher version

### Compatibility Rules

**Compatible:**
- Same `training_mode` (single_symbol vs multi_symbol)
- Same `symbol_encoding_type` (if multi_symbol mode)
- All required files exist

**Incompatible:**
- Different `training_mode`
- Different `symbol_encoding_type` (for multi_symbol)
- Missing files (model, scaler, or config)

### Example Selection

**Config:**
```yaml
model:
  training_mode: multi_symbol
  symbol_encoding: one_hot
```

**Available Models:**
1. v1.0: `training_mode=single_symbol` → ❌ Incompatible
2. v1.1: `training_mode=multi_symbol`, `symbol_encoding_type=one_hot`, 5 symbols → ✅ Compatible
3. v1.2: `training_mode=multi_symbol`, `symbol_encoding_type=index` → ❌ Incompatible (encoding mismatch)
4. v2.0: `training_mode=multi_symbol`, `symbol_encoding_type=one_hot`, 10 symbols → ✅ Compatible (better)

**Selected:** v2.0 (more symbols, higher version)

## Integration Points

### 1. Training Script (`train_model.py`)

**Before Training:**
- Calls `select_best_model(config)` to check for compatible model
- If found and `--force-train` not set:
  - **Skips training**
  - Logs model info
  - Exits with success (return code 0)
- If `--force-train` is set:
  - Proceeds with training
  - Auto-increments version if compatible model exists

**Version Handling:**
- `--version X.Y`: Use explicit version
- `--force-train` + existing model: Auto-increment (e.g., 1.0 → 1.1)
- Default: Use `config.model.version` (usually "1.0")

### 2. Installer (`install.sh`)

**Before Training Prompt:**
- Checks for existing compatible model using Python helper
- If found:
  - Shows model info (version, symbols, etc.)
  - Prompts: "Do you want to retrain anyway?"
  - Default: **NO** (reuse existing)
  - If yes: Adds `--force-train` flag
- If not found:
  - Proceeds with normal training prompt

### 3. Live Bot (`live_bot.py`)

**Current Behavior (Not Changed):**
- Uses `get_model_paths(config)` to get model paths from config
- Loads model from hard-coded config paths
- **Future Enhancement**: Could use model registry to auto-select best model

### 4. Scheduled Retraining (`scripts/scheduled_retrain.py`)

**Current Behavior:**
- Checks model age (file modification time)
- **Future Enhancement**: Could use model registry to check compatibility before retraining

## Usage Examples

### Check Available Models

```bash
python scripts/list_models.py
```

Output:
```
============================================================
MODEL DISCOVERY
============================================================

Found 2 model version(s):

1. Model v1.0
   Files exist: True
   Training Mode: single_symbol
   Symbol Encoding: unknown
   Trained Symbols: 1
      BTCUSDT
   Training Days: 730
   Training End: 2025-12-04T12:00:00

2. Model v1.1
   Files exist: True
   Training Mode: multi_symbol
   Symbol Encoding: one_hot
   Trained Symbols: 5
      BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, LINKUSDT
   Training Days: 730
   Training End: 2025-12-05T10:00:00

============================================================
MODEL SELECTION (for current config)
============================================================

Config requirements:
  Training Mode: multi_symbol
  Symbol Encoding: one_hot

Selected model:
------------------------------------------------------------
Version: 1.1
Training Mode: multi_symbol
Symbol Encoding: one_hot
Trained Symbols: 5 (BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, LINKUSDT)
Training Days: 730
Training End: 2025-12-05T10:00:00
Files Exist: True
------------------------------------------------------------
```

### Train with Model Check

```bash
# Normal training (skips if compatible model exists)
python train_model.py --symbol BTCUSDT

# Force training (always trains, creates new version)
python train_model.py --symbol BTCUSDT --force-train

# Explicit version
python train_model.py --symbol BTCUSDT --version 2.0
```

## Backward Compatibility

### Old Models Without Metadata

Models trained before this system was implemented may not have full metadata in `model_config_v*.json`. The system handles this gracefully:

- **Missing `training_mode`**: Assumes `'single_symbol'` (backward compatible)
- **Missing `symbol_encoding_type`**: Assumes `'one_hot'` (default)
- **Missing `trained_symbols`**: Empty list (model may still work but won't be preferred)
- **Missing files**: Model marked as incomplete, skipped during selection

### Migration Path

1. **Existing models**: Will be discovered and can be used if compatible
2. **New training**: Automatically saves full metadata
3. **Gradual migration**: Old models can be retrained to add metadata

## Configuration

Model discovery uses these config values:

```yaml
model:
  training_mode: single_symbol  # or multi_symbol
  symbol_encoding: one_hot      # or index (only for multi_symbol)
  version: "1.0"                 # Default version for new models
```

## Files

- **Registry Module**: `src/models/model_registry.py`
- **Diagnostic Script**: `scripts/list_models.py`
- **Documentation**: This file

## Future Enhancements

Potential improvements:
1. **Auto-selection in live_bot**: Use registry to select best model on startup
2. **Model validation**: Check model performance before selection
3. **Symbol coverage requirements**: Require minimum symbol coverage
4. **Model age limits**: Prefer models trained within last N days
5. **Performance-based selection**: Prefer models with better backtest metrics

