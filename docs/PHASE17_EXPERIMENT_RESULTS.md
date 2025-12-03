# Phase 17: Experiment Results & Calibration

## Experiment Plan

### Objective
Execute comprehensive walk-forward backtests to identify robust, data-driven default configurations for the v2.1 bot.

### Symbols
- **Primary**: BTCUSDT, ETHUSDT (MUST)
- **Optional**: BNBUSDT, SOLUSDT, XRPUSDT (if data available)

### Time Horizon
- **Target**: ≥ 2 years per symbol
- **Minimum**: 1 year (for quick tests)

### Configuration Dimensions

#### 1. Risk Profiles (3 levels)
- **Conservative**: Leverage 2x, base 1%, max 5%, conf 0.65
- **Moderate**: Leverage 3x, base 2%, max 10%, conf 0.60
- **Aggressive**: Leverage 5x, base 3%, max 15%, conf 0.55

#### 2. Ensemble Settings (2 options)
- **On**: XGBoost 70% + Logistic Regression 30%
- **Off**: Pure XGBoost only

#### 3. Portfolio Layer (2 options)
- **Off**: All symbols tradable
- **On**: Top-K selection (K=3, daily rebalance)

#### 4. Regime Filter Sensitivity (3 levels)
- **Strict**: ADX threshold 30
- **Moderate**: ADX threshold 25 (default)
- **Lenient**: ADX threshold 20

#### 5. Triple-Barrier Parameters (1 default set for initial runs)
- **Default**: Profit 2%, Loss 1%, Time 24h
- (Can expand to 3 sets: tight/moderate/wide in future runs)

#### 6. Performance Guard Thresholds
- Embedded in risk profiles (conservative/moderate/aggressive)

### Total Configurations
- **Full Grid**: 3 × 2 × 2 × 3 × 1 = 36 configs per symbol
- **Initial Run**: Focus on conservative + moderate, ensemble on/off = 2 × 2 × 1 × 1 × 1 = 4 configs per symbol

### Execution Strategy

**Phase 1: Quick Validation (1-2 hours)**
```bash
python research/run_research_suite.py \
  --quick \
  --symbols BTCUSDT \
  --years 1
```

**Phase 2: Core Experiments (4-8 hours)**
```bash
python research/run_research_suite.py \
  --symbols BTCUSDT ETHUSDT \
  --years 2 \
  --risk-levels conservative moderate \
  --ensemble true false \
  --portfolio false \
  --regime moderate \
  --output-dir research_results/core
```

**Phase 3: Full Grid (1-2 days)**
```bash
python research/run_research_suite.py \
  --symbols BTCUSDT ETHUSDT \
  --years 2 \
  --risk-levels conservative moderate aggressive \
  --ensemble true false \
  --portfolio false true \
  --regime strict moderate lenient \
  --output-dir research_results/full
```

### Requirements
- ✅ Realistic costs (fees 0.05%, slippage 0.01%, funding 0.01% per 8h)
- ✅ No look-ahead bias (walk-forward validation)
- ✅ Minimum 30 trades per config (filter out insufficient data)

---

## Results Summary

**Status:** ⚠️ **AWAITING EXECUTION**

Results will be populated by running the research harness. This section will contain:

### Best Performing Configurations

**Conservative Profile:**
- Config: [To be determined]
- Sharpe: [TBD]
- Profit Factor: [TBD]
- Max Drawdown: [TBD]
- Stability (CV): [TBD]

**Moderate Profile:**
- Config: [To be determined]
- Sharpe: [TBD]
- Profit Factor: [TBD]
- Max Drawdown: [TBD]
- Stability (CV): [TBD]

### Robust Configurations (Stable Across Periods)

**Most Robust:**
- Config: [To be determined]
- CV: [TBD]
- Performance across periods: [TBD]

---

## Key Findings (To Be Populated)

### 1. Ensemble Impact
- **Question**: Does ensemble improve robustness?
- **Finding**: [TBD]
- **Recommendation**: [TBD]

### 2. Regime Filter Impact
- **Question**: Does regime filter improve risk-adjusted returns?
- **Finding**: [TBD]
- **Recommendation**: [TBD]

### 3. Portfolio Layer Impact
- **Question**: Does cross-sectional selection improve performance?
- **Finding**: [TBD]
- **Recommendation**: [TBD]

### 4. Risk Profile Comparison
- **Question**: Which risk profile offers best risk-adjusted returns?
- **Finding**: [TBD]
- **Recommendation**: [TBD]

### 5. Parameter Sensitivity
- **Question**: Which parameters are most/least sensitive?
- **Finding**: [TBD]
- **Recommendation**: [TBD]

---

## Results Tables (To Be Populated)

### By Symbol and Risk Level

| Symbol | Risk | Ensemble | Portfolio | Regime | Sharpe | PF | Max DD | Win Rate | Trades | CV |
|--------|------|----------|-----------|--------|--------|----|----|----------|--------|-----|
| BTCUSDT | Cons | On | Off | Mod | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| BTCUSDT | Cons | Off | Off | Mod | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| BTCUSDT | Mod | On | Off | Mod | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

### Top 5 Configurations by Sharpe Ratio

| Rank | Config ID | Symbol | Sharpe | PF | Max DD | Stability |
|------|-----------|--------|--------|----|----|-----------|
| 1 | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| 2 | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| ... | ... | ... | ... | ... | ... | ... |

### Fragility Analysis

**High Fragility (CV > 0.5):**
- [To be determined]

**Low Fragility (CV < 0.3):**
- [To be determined]

---

## Key Takeaways (To Be Populated)

### Where the System Looks Strongest
- [TBD]

### Where It Breaks
- [TBD]

### Surprising Parameter Sensitivities
- [TBD]

### Recommendations
- [TBD]

---

## Execution Instructions

### Prerequisites
1. Ensure historical data is available or can be downloaded
2. Verify config file is properly set up
3. Check disk space (results can be large)

### Running Experiments

**Quick Test:**
```bash
python research/run_research_suite.py --quick
```

**Core Experiments:**
```bash
python research/run_research_suite.py \
  --symbols BTCUSDT ETHUSDT \
  --years 2 \
  --risk-levels conservative moderate \
  --ensemble true false \
  --output-dir research_results/core
```

**Full Grid:**
```bash
python research/run_research_suite.py \
  --symbols BTCUSDT ETHUSDT \
  --years 2 \
  --risk-levels conservative moderate aggressive \
  --ensemble true false \
  --portfolio false true \
  --regime strict moderate lenient \
  --output-dir research_results/full
```

### Expected Runtime
- Quick test: 30-60 minutes
- Core experiments: 4-8 hours
- Full grid: 1-2 days

### Output Files
- `research_results/all_results.csv` - Aggregated results
- `research_results/{symbol}_{config_id}_result.json` - Individual results
- `research_results/PHASE17_EXPERIMENT_RESULTS.md` - This report (auto-generated)

---

## Notes

- **Results are from backtesting**: Not guarantees of future performance
- **Market conditions vary**: Results may differ in live trading
- **Costs are modeled**: Real costs may vary
- **No look-ahead bias**: Walk-forward validation ensures realistic results
- **Minimum trade count**: Configs with < 30 trades are filtered

---

## Status

**Current Status:** ⚠️ **AWAITING EXECUTION**

This document serves as a template and experiment plan. Results should be populated by:
1. Running `research/run_research_suite.py` with appropriate arguments
2. Analyzing output CSV/JSON files
3. Updating this document with findings
4. Refining recommended defaults in `config/config.yaml`

**Next Steps:**
1. Execute quick test to validate harness
2. Run core experiments
3. Analyze results and populate this document
4. Refine defaults based on evidence

---

**Date:** December 2025  
**Status:** Experiment Plan - Ready for Execution
