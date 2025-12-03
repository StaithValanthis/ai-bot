# install.sh Updates for Universe Feature

## Summary

The `install.sh` script has been updated to include **universe mode selection** and related configuration during installation.

## Changes Made

### 1. Universe Mode Selection Prompt ✅

**Location**: Step 3 (Configuration section)

**Added**:
- Prompt for universe mode selection:
  - `[1] fixed` - Recommended for first deployment (uses explicit symbol list)
  - `[2] auto` - Dynamic discovery from Bybit (requires API access)
- Default: `fixed` (safe default)

### 2. Universe Settings Prompts (Auto Mode) ✅

**Location**: After universe mode selection

**Added** (only if auto mode selected):
- `min_usd_volume_24h`: Minimum 24h USD volume filter (default: 50000000 = $50M)
- `max_symbols`: Maximum symbols to include (default: 10 for testing, 30 for production)

### 3. Config.yaml Update ✅

**Location**: Step 4 (Writing configuration files)

**Added**:
- Automatic update of `config/config.yaml` with universe settings
- Backs up existing config.yaml before updating
- Uses Python YAML library for reliable YAML manipulation
- Updates:
  - `exchange.universe_mode`
  - `exchange.min_usd_volume_24h` (if auto mode)
  - `exchange.max_symbols` (if auto mode)

### 4. Data Fetch Enhancement ✅

**Location**: Step 6 (Optional initial setup steps)

**Added**:
- If auto universe mode selected:
  - Option to test universe discovery first (recommended)
  - Option to fetch data for specific symbols
- If fixed mode: Standard symbol prompt

### 5. Verification Updates ✅

**Location**: Step 7 (Verification)

**Added**:
- Checks for `yaml` package (needed for config.yaml updates)
- Tests universe module import if auto mode selected

### 6. Documentation References ✅

**Location**: Final summary (Next Steps)

**Added**:
- Step 6: Test universe discovery (if using auto mode)
- Step 7: Review documentation includes:
  - `docs/UNIVERSE_MANAGEMENT.md` (if using auto mode)
  - `docs/UNIVERSE_VALIDATION_REPORT.md`

### 7. Final Summary Updates ✅

**Location**: Final summary

**Added**:
- Shows universe mode in configuration files section
- Shows universe cache path if auto mode
- Shows fixed mode info if fixed mode

## Installation Flow

### Step-by-Step with Universe Mode

1. **Pre-flight checks** (unchanged)
2. **Virtual environment setup** (unchanged)
3. **Configuration prompts**:
   - Bybit API credentials
   - Testnet vs Live
   - **NEW**: Universe mode selection (fixed/auto)
   - **NEW**: Universe settings (if auto mode)
   - Trading profile
   - Discord webhook
4. **Write configuration files**:
   - Write/update `.env`
   - **NEW**: Update `config.yaml` with universe settings
5. **Optional systemd setup** (unchanged)
6. **Optional initial steps**:
   - **ENHANCED**: Data fetch (handles universe mode)
   - Model training (unchanged)
7. **Verification**:
   - **ENHANCED**: Check universe module (if auto mode)
   - Other checks (unchanged)

## Example Installation Session

```
==========================================
  Bybit AI Trading Bot v2.1+ Installer
==========================================

[INFO] Step 3: Configuration
[INFO] Universe Discovery Mode:
  [1] fixed (Recommended for first deployment - uses explicit symbol list)
  [2] auto (Dynamic discovery from Bybit - requires API access)
Enter universe mode [1-2]: 2
[INFO] Selected: Auto mode (will discover symbols dynamically)
[WARN] Auto mode requires API access and makes additional API calls

[INFO] Universe Filtering Settings (for auto mode):
Minimum 24h USD volume (e.g., 50000000 for $50M) [default: 50000000]: 50000000
Maximum symbols to include (e.g., 10 for testing, 30 for production) [default: 10]: 10
[INFO] Universe will filter symbols with >= $50M volume, max 10 symbols

[INFO] Step 4: Writing configuration files...
[INFO] Updating config.yaml with universe settings...
[INFO] Config backup created: config/config.yaml.backup_20251203_214900
[SUCCESS] config.yaml updated with universe settings
```

## Backward Compatibility

- **Default behavior**: If user selects fixed mode (default), behavior is identical to before
- **Existing configs**: Script backs up config.yaml before updating
- **Manual override**: Users can always edit config.yaml manually if needed

## Testing Recommendations

1. **Test fixed mode installation**:
   ```bash
   bash install.sh
   # Select: fixed mode
   # Verify: config.yaml has universe_mode: fixed
   ```

2. **Test auto mode installation**:
   ```bash
   bash install.sh
   # Select: auto mode
   # Enter: min_volume=50000000, max_symbols=10
   # Verify: config.yaml has universe_mode: auto with correct settings
   ```

3. **Test universe discovery**:
   ```bash
   source venv/bin/activate
   python scripts/test_universe.py
   ```

## Files Modified

- `install.sh`: Added universe mode selection and config.yaml updates

## Related Documentation

- `docs/UNIVERSE_MANAGEMENT.md` - User guide for universe feature
- `docs/UNIVERSE_VALIDATION_REPORT.md` - Validation results
- `docs/UNIVERSE_FEATURE_SUMMARY.md` - Quick reference

