# Model Architecture Options: Shared vs Per-Symbol vs Hybrid

**Date**: 2025-12-03  
**Status**: Analysis & Recommendation

---

## Executive Summary

This document analyzes three approaches to organizing ML models for multi-symbol trading:

1. **Improved Shared Global Model** - Train on aggregated multi-symbol data with symbol encoding
2. **Per-Symbol Models** - Separate model per symbol
3. **Hybrid Approach** - Shared base with symbol-specific fine-tuning/calibration

**Current State**: The bot trains on a single symbol (typically BTCUSDT) but applies the same model to all symbols during live trading. The model has no awareness of which symbol it's predicting for.

**Recommendation**: **Option A (Improved Shared Global Model)** with phased implementation:
- **Phase 1**: Multi-symbol training with simple symbol encoding
- **Phase 2**: Empirical comparison vs per-symbol models
- **Phase 3**: Consider hybrid if Phase 2 shows clear benefits

---

## Current Implementation Analysis

### Verified Behavior

**Training (`train_model.py`)**:
- Lines 127-133: If multiple symbols are discovered, only the **first symbol** is used for training
- Model is saved to generic path: `models/meta_model_v1.0.joblib` (not symbol-specific)
- Training data comes from a single symbol's history

**Live Trading (`live_bot.py`)**:
- Lines 67-71: **One** `MetaPredictor` instance is created at startup
- Line 188: `confidence = self.meta_predictor.predict(meta_features)` - no symbol identifier passed
- The same model is reused for all symbols (BTCUSDT, ETHUSDT, SOLUSDT, etc.)

**Model Training (`src/models/train.py`)**:
- `prepare_data()` takes a `symbol` parameter but only uses it for logging
- No symbol-specific features or encodings are added to the feature set
- Features are purely technical indicators (RSI, MACD, EMA, etc.) with no symbol identity

**MetaPredictor (`src/signals/meta_predictor.py`)**:
- `predict()` method takes a features dict but no symbol identifier
- Model has no way to distinguish between BTCUSDT and ETHUSDT features

### Implications

- **Generalization Assumption**: The model implicitly assumes patterns learned from BTCUSDT generalize to all symbols
- **No Symbol Awareness**: The model cannot adapt its predictions based on which symbol it's evaluating
- **Potential Issues**:
  - Volatility regimes differ significantly between BTC and altcoins
  - Market microstructure varies (liquidity, funding behavior, noise structure)
  - Correlation structures differ (BTC may trend while alts range, or vice versa)

---

## Option A: Improved Shared Global Model

### Description

Train a single model on **aggregated data from multiple symbols** (e.g., BTCUSDT, ETHUSDT, SOLUSDT, etc.). Add a symbol identifier feature (one-hot encoding, learned embedding, or simple index) so the model can learn symbol-specific patterns while sharing common patterns.

**High-Level Flow**:
1. Collect historical data for multiple symbols (top N by liquidity)
2. Combine all data into a unified training dataset
3. Add a `symbol_id` feature (one-hot or embedding)
4. Train one model on the combined dataset
5. During live trading, pass the symbol identifier along with features

### Pros

**Generalization**:
- Model learns both common patterns (trend-following, regime detection) and symbol-specific nuances
- More robust to regime shifts if trained across diverse symbols
- Better statistical power from larger combined dataset

**Statistical Robustness**:
- Significantly more training samples (N symbols × T time periods)
- Better coverage of market regimes (bull, bear, ranging, volatile)
- Reduced overfitting risk due to larger dataset

**Operational Simplicity**:
- Single model to maintain, retrain, and monitor
- No combinatorial explosion of models
- Easier to version control and deploy
- Existing infrastructure (auto-retrain, research harness) works with minimal changes

**Fit with Infrastructure**:
- Works seamlessly with UniverseManager (just aggregate discovered symbols)
- Portfolio layer can still select symbols, model provides confidence scores
- Research harness can easily compare single vs multi-symbol training
- Config structure remains simple (one model path)

### Cons

**Over/Underfitting Risk**:
- Risk of overfitting to dominant symbol (e.g., BTC) if not balanced
- Risk of underfitting if symbol differences are too large
- Need careful data balancing or weighting

**Compute/Training Time**:
- Training time increases with number of symbols (but still manageable)
- More memory required during training (but modern systems handle this)

**Complexity**:
- Need to handle symbol encoding (one-hot adds dimensionality)
- Must ensure feature consistency across symbols
- Symbol identifier must be passed correctly during live trading

**Data Requirements**:
- Need quality data for multiple symbols (already have this via UniverseManager)
- Must ensure all symbols have sufficient history (already checked in data pipeline)

### Data Requirements

- **Per Symbol**: Same as current (2+ years, 1h candles)
- **Total**: N symbols × T time periods (e.g., 10 symbols × 17,520 hours = 175,200 samples)
- **Symbol Encoding**: One-hot encoding adds N-1 features (or learned embedding adds K features)

### Fit with Existing Infrastructure

**UniverseManager**: ✅ Perfect fit
- Can aggregate data from all discovered symbols
- Filtering (liquidity, price) ensures quality symbols

**Portfolio Layer**: ✅ Compatible
- Model provides confidence scores per symbol
- Portfolio selector uses these scores for allocation

**Research Harness**: ✅ Easy integration
- Can compare single-symbol vs multi-symbol training
- Walk-forward validation works the same way

**Auto-Retrain Pipeline**: ✅ Minimal changes
- Still trains one model, just on more data
- Same model path structure

**Config Structure**: ✅ Simple
- Add `model.training_mode: "multi_symbol"` flag
- Keep existing model path structure

### Implementation Changes

**`train_model.py`**:
- Accept `--symbols` (list) or use universe manager to get all symbols
- Loop over symbols, download data for each
- Combine all DataFrames, add `symbol_id` column (one-hot or index)
- Train single model on combined dataset
- Save to same generic path (backward compatible)

**`src/models/train.py`**:
- Modify `prepare_data()` to accept list of DataFrames (one per symbol)
- Add symbol encoding logic (one-hot or embedding)
- Ensure feature consistency across symbols

**`src/signals/features.py`**:
- Add `symbol_id` to meta-features when building feature dict
- Ensure symbol identifier is passed through feature pipeline

**`live_bot.py`**:
- When building meta-features, include symbol identifier
- Ensure `MetaPredictor.predict()` receives symbol_id in features dict

**Config**:
- Add `model.training_mode: "single_symbol" | "multi_symbol"`
- Add `model.symbol_encoding: "one_hot" | "index" | "embedding"` (start with one_hot)

---

## Option B: Per-Symbol Models

### Description

Train a **separate model for each symbol**. Each symbol gets its own model file, scaler, and config. During live trading, load the appropriate model for each symbol when making predictions.

**High-Level Flow**:
1. For each symbol in universe:
   - Download historical data
   - Train model on that symbol's data only
   - Save to `models/meta_model_<SYMBOL>_v1.0.joblib`
2. During live trading:
   - Maintain a dict of `MetaPredictor` instances keyed by symbol
   - Load models on-demand or at startup
   - Use symbol-specific model for each prediction

### Pros

**Generalization**:
- Each model is tailored to its symbol's specific dynamics
- No assumption that BTC patterns apply to altcoins
- Can capture symbol-specific volatility regimes and microstructure

**Statistical Robustness**:
- Model parameters optimized for each symbol's data distribution
- No risk of overfitting to dominant symbol
- Better fit to symbol-specific patterns

**Operational Flexibility**:
- Can retrain individual symbols independently
- Can disable trading for symbols with poor models
- Easy to A/B test model improvements per symbol

### Cons

**Over/Underfitting Risk**:
- Each model has less data (one symbol vs aggregated)
- Higher risk of overfitting to single symbol's history
- Less robust to regime shifts (trained on one symbol's regimes only)

**Compute/Training Time**:
- Training time scales linearly with number of symbols (10 symbols = 10x training time)
- More storage required (10 models vs 1)
- More complex retraining pipeline (need to track which models are stale)

**Complexity**:
- More complex deployment (multiple model files to manage)
- More complex monitoring (track performance per symbol-model pair)
- More complex versioning (each symbol can have different model versions)
- Research harness needs to handle per-symbol models

**Data Requirements**:
- Same per-symbol requirements, but no aggregation benefit
- Each symbol needs sufficient history (already have this)

### Data Requirements

- **Per Symbol**: Same as current (2+ years, 1h candles)
- **Total**: Same as single-symbol training (no aggregation)
- **Storage**: N model files instead of 1

### Fit with Existing Infrastructure

**UniverseManager**: ⚠️ Requires changes
- Need to train models for all discovered symbols
- Must handle symbols being added/removed from universe

**Portfolio Layer**: ✅ Compatible
- Still provides confidence scores per symbol
- Can weight by model quality if desired

**Research Harness**: ⚠️ More complex
- Need to train per-symbol models for each fold
- More storage and compute required

**Auto-Retrain Pipeline**: ⚠️ Significant changes
- Need to track which symbols need retraining
- More complex scheduling (retrain all vs selective)
- More storage management

**Config Structure**: ⚠️ More complex
- Need model path patterns per symbol
- Need to handle missing models gracefully

### Implementation Changes

**`train_model.py`**:
- Accept `--symbols` (list) or use universe manager
- Loop over symbols, train one model per symbol
- Save to `models/meta_model_<SYMBOL>_v1.0.joblib`
- Option to train all symbols or specific subset

**`src/models/train.py`**:
- Mostly unchanged (still trains on single symbol's data)
- Save logic needs symbol-specific paths

**`src/signals/meta_predictor.py`**:
- Option 1: Create `MultiSymbolMetaPredictor` wrapper that manages dict of predictors
- Option 2: Modify `live_bot.py` to maintain dict of predictors

**`live_bot.py`**:
- Maintain `self.meta_predictors: Dict[str, MetaPredictor]` instead of single predictor
- Load models on-demand or at startup
- Fallback gracefully if model missing (skip trading that symbol, log warning)

**Config**:
- Add `model.training_mode: "per_symbol"`
- Add `model.model_path_pattern: "models/meta_model_{symbol}_v{version}.joblib"`
- Add `model.fallback_to_shared: true` (use shared model if symbol-specific missing)

---

## Option C: Hybrid Approach

### Description

Combine elements of A and B: train a **shared base model** on multi-symbol data, then add **symbol-specific fine-tuning or calibration layers**. This could take several forms:

1. **Fine-Tuning**: Pre-train on multi-symbol data, then fine-tune last layer(s) per symbol
2. **Calibration**: Shared model + per-symbol calibration (e.g., Platt scaling per symbol)
3. **Clustering**: Group symbols (majors vs alts), train one model per cluster
4. **Adapter Layers**: Shared base + small per-symbol adapter networks

**High-Level Flow** (Fine-Tuning variant):
1. Train base model on aggregated multi-symbol data (like Option A)
2. For each symbol:
   - Load base model
   - Freeze early layers, fine-tune last layer(s) on symbol-specific data
   - Save fine-tuned model
3. During live trading:
   - Use symbol-specific fine-tuned model (or fallback to base)

### Pros

**Generalization**:
- Best of both worlds: common patterns from shared model, symbol-specific adaptation
- More robust than pure per-symbol (benefits from multi-symbol training)
- More tailored than pure shared (symbol-specific fine-tuning)

**Statistical Robustness**:
- Base model benefits from large aggregated dataset
- Fine-tuning adapts to symbol-specific patterns with less data
- Lower risk of overfitting (fine-tuning uses fewer parameters)

**Operational Flexibility**:
- Can fine-tune individual symbols independently
- Base model provides fallback if fine-tuning fails
- Can cluster symbols for efficiency (fewer models than per-symbol)

### Cons

**Over/Underfitting Risk**:
- Fine-tuning can overfit if symbol data is limited
- Need to balance base model capacity vs fine-tuning scope
- More complex hyperparameter tuning

**Compute/Training Time**:
- Two-stage training (base + fine-tuning) takes longer
- Still need to train per-symbol (though faster than full training)
- More complex training pipeline

**Complexity**:
- Most complex approach (two-stage training, per-symbol fine-tuning)
- More complex deployment (base + fine-tuned models)
- More complex monitoring and versioning
- Research harness needs to handle both stages

**Data Requirements**:
- Need multi-symbol data for base model
- Need per-symbol data for fine-tuning
- More storage (base + N fine-tuned models)

### Data Requirements

- **Base Model**: Multi-symbol aggregated data (like Option A)
- **Fine-Tuning**: Per-symbol data (can be smaller, e.g., 6 months)
- **Storage**: 1 base model + N fine-tuned models

### Fit with Existing Infrastructure

**UniverseManager**: ⚠️ Requires changes
- Need to train base model on all symbols
- Then fine-tune per symbol

**Portfolio Layer**: ✅ Compatible
- Still provides confidence scores per symbol

**Research Harness**: ⚠️ Complex
- Need to handle two-stage training
- More compute and storage

**Auto-Retrain Pipeline**: ⚠️ Very complex
- Need to retrain base model periodically
- Then fine-tune all symbols
- Complex scheduling and versioning

**Config Structure**: ⚠️ Complex
- Need base model path + fine-tuned model pattern
- Need fine-tuning hyperparameters

### Implementation Changes

**`train_model.py`**:
- Stage 1: Train base model on multi-symbol data
- Stage 2: Loop over symbols, fine-tune base model per symbol
- Save base model + fine-tuned models

**`src/models/train.py`**:
- Add fine-tuning logic (freeze layers, train last layer(s))
- Support loading base model and fine-tuning

**`src/signals/meta_predictor.py`**:
- Support loading fine-tuned models with base model fallback

**`live_bot.py`**:
- Load fine-tuned models per symbol, fallback to base if missing

**Config**:
- Add `model.training_mode: "hybrid"`
- Add `model.base_model_path: "models/meta_model_base_v1.0.joblib"`
- Add `model.fine_tuned_path_pattern: "models/meta_model_{symbol}_ft_v{version}.joblib"`
- Add fine-tuning hyperparameters

---

## Recommendation: Option A (Improved Shared Global Model)

### Justification

**Why Option A**:
1. **Operational Simplicity**: Single model is easier to maintain, monitor, and deploy
2. **Statistical Robustness**: Larger aggregated dataset reduces overfitting risk
3. **Infrastructure Fit**: Minimal changes to existing codebase and workflows
4. **Empirical Evidence**: Multi-symbol training with symbol encoding is a proven approach in quantitative finance
5. **Phased Approach**: Can start simple (one-hot encoding) and evolve (embeddings, clustering)

**Why Not Option B**:
- Operational complexity (N models to manage) outweighs potential benefits
- Higher overfitting risk per symbol (less data per model)
- Training time scales poorly with universe size
- Current infrastructure doesn't support per-symbol model management well

**Why Not Option C**:
- Too complex for initial implementation
- Fine-tuning adds significant operational overhead
- Benefits over Option A are uncertain without empirical validation
- Can be explored later if Option A shows limitations

### Trade-offs Accepted

- **Symbol-Specific Nuances**: We accept that a shared model may not capture all symbol-specific patterns, but we gain robustness and simplicity
- **Training Data Balance**: We may need to balance or weight symbols to avoid overfitting to dominant symbols (e.g., BTC)
- **Feature Dimensionality**: One-hot encoding adds N-1 features (manageable for 10-30 symbols)

### Phased Implementation Plan

**Phase 1: Multi-Symbol Training with Simple Encoding** (Recommended First Step)
- Implement multi-symbol data aggregation in `train_model.py`
- Add one-hot symbol encoding to feature set
- Train single model on combined dataset
- Update `live_bot.py` to pass symbol identifier
- Add config flag `model.training_mode: "multi_symbol"`
- Keep backward compatibility (single-symbol training still works)

**Phase 2: Empirical Comparison**
- Use research harness to compare:
  - Current: Single-symbol trained (BTCUSDT), shared model
  - New: Multi-symbol trained (BTCUSDT + ETHUSDT + SOLUSDT + ...), shared model
- Metrics: Sharpe, PF, max DD, stability across symbols and time periods
- Run on 2+ years of data for BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, LINKUSDT

**Phase 3: Decision Point**
- If multi-symbol training shows clear benefits: adopt as default
- If per-symbol models show promise: implement Option B for top 3-5 symbols
- If hybrid shows value: explore Option C with clustering (majors vs alts)

---

## Empirical Validation Plan

### Comparison Setup

**Models to Compare**:
1. **Baseline**: Single-symbol trained (BTCUSDT only), shared model (current approach)
2. **Multi-Symbol**: Multi-symbol trained (BTCUSDT + ETHUSDT + SOLUSDT + DOGEUSDT + LINKUSDT), shared model with one-hot encoding

**Symbols**:
- Primary: BTCUSDT, ETHUSDT
- Secondary: SOLUSDT, DOGEUSDT, LINKUSDT
- Total: 5 symbols

**Time Horizon**:
- Training: 2 years of history (730 days)
- Testing: Walk-forward validation with 180-day train, 30-day test, 30-day step
- Total backtest period: 2 years

**Metrics**:
- **Sharpe Ratio**: Risk-adjusted returns
- **Profit Factor**: Gross profit / gross loss
- **Max Drawdown**: Maximum peak-to-trough decline
- **Win Rate**: Percentage of profitable trades
- **Trade Count**: Number of trades executed
- **Stability**: Performance consistency across sub-periods and symbols

### Procedure

1. **Data Preparation**:
   - Download 2+ years of 1h candles for all 5 symbols
   - Ensure data quality (no gaps, duplicates, etc.)

2. **Model Training**:
   - Train baseline model on BTCUSDT only
   - Train multi-symbol model on all 5 symbols with one-hot encoding
   - Use same hyperparameters for fair comparison

3. **Walk-Forward Backtesting**:
   - Use existing research harness (`research/run_research_suite.py`)
   - Run walk-forward validation for both models
   - Test on each symbol separately (to see generalization)
   - Aggregate results across symbols

4. **Analysis**:
   - Compare metrics side-by-side
   - Check if multi-symbol model generalizes better to unseen symbols
   - Check if multi-symbol model is more stable across time periods
   - Identify any symbols where single-symbol model performs better

5. **Documentation**:
   - Save results to `research_results/model_architecture_comparison/`
   - Generate comparison report
   - Update this document with findings

### Expected Outcomes

**If Multi-Symbol Training Wins**:
- Adopt as default training mode
- Document best practices (symbol selection, encoding method)
- Consider expanding to more symbols or exploring embeddings

**If Single-Symbol Training Wins**:
- Keep current approach
- Consider per-symbol models for top symbols only
- Investigate why multi-symbol didn't help (data quality, encoding method, etc.)

**If Results Are Mixed**:
- Use multi-symbol for some symbols, single-symbol for others
- Consider hybrid approach (clustering)
- Further investigation needed

---

## Implementation Details

### Code Changes Summary

**Files to Modify**:
1. `train_model.py` - Multi-symbol data aggregation
2. `src/models/train.py` - Symbol encoding in feature preparation
3. `src/signals/features.py` - Add symbol_id to meta-features
4. `live_bot.py` - Pass symbol identifier to predictor
5. `config/config.yaml` - Add training mode config

**New Files**:
- None (all changes are additive, backward compatible)

**Config Changes**:
```yaml
model:
  training_mode: "multi_symbol"  # "single_symbol" | "multi_symbol"
  symbol_encoding: "one_hot"     # "one_hot" | "index" | "embedding"
  multi_symbol_symbols: []       # Empty = use universe, or explicit list
```

### Backward Compatibility

- Single-symbol training remains available via `--symbol` flag
- Config defaults to `training_mode: "single_symbol"` for safety
- Existing model files continue to work
- Research harness supports both modes

---

## Conclusion

**Recommended Approach**: **Option A (Improved Shared Global Model)** with phased implementation.

**Rationale**: Operational simplicity, statistical robustness, and minimal infrastructure changes make this the best starting point. Empirical validation will guide future decisions.

**Next Steps**:
1. Implement Phase 1 (multi-symbol training scaffolding)
2. Run empirical comparison (Phase 2)
3. Make data-driven decision (Phase 3)

**Uncertainty**: This recommendation is based on conceptual analysis and industry best practices. Empirical validation is essential before committing to any approach long-term.

---

**Document Status**: ✅ Complete - Ready for implementation

