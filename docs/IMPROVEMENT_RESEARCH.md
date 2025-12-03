# Improvement Research: Evidence-Backed Enhancements

## Overview

This document summarizes concrete, evidence-backed improvements that could realistically improve the bot's robustness and long-run risk-adjusted performance for crypto perpetual futures trading. Each improvement is linked to its source (academic papers, quant blogs, open-source repos) and explains relevance to this specific bot.

---

## 1. Triple-Barrier Meta-Labeling

### Source
- **Lopez de Prado, M. (2018).** *Advances in Financial Machine Learning*. Wiley. Chapter 7: "Labeling".

### Concept
Instead of simple binary labels (profitable/not), use **triple-barrier method**:
- **Profit barrier**: Exit if price moves in favor by X% (e.g., +2%)
- **Loss barrier**: Exit if price moves against by Y% (e.g., -1%)
- **Time barrier**: Exit after maximum holding period (e.g., 24 hours)

Labels become:
- `1` if profit barrier hit first
- `0` if loss barrier hit first
- `0` if time barrier hit (neutral/unprofitable)

### Why Relevant
- **More realistic**: Models actual trading with stop-losses and take-profits
- **Better labels**: Distinguishes between "small loss" and "timeout" scenarios
- **Reduces overfitting**: More nuanced labels prevent model from learning unrealistic patterns

### Expected Benefits
- More accurate profitability prediction
- Better alignment with live trading (early exits)
- Improved risk-adjusted returns

### Possible Downsides
- More complex label generation
- Requires careful barrier selection (may need optimization)

### Implementation Notes
- Replace simple hold-period logic in `src/models/train.py` `prepare_data()`
- Add barrier parameters to config
- Track which barrier was hit for analysis

---

## 2. Regime Classification & Filtering

### Source
- **Lopez de Prado, M. (2018).** *Advances in Financial Machine Learning*. Chapter 8: "Sample Weights and Imbalanced Classes".
- **Multiple academic papers** on regime-switching models in finance
- **Freqtrade** and other open-source bots use regime filters

### Concept
Classify market into regimes:
- **Trending Up**: Clear uptrend (ADX > 25, price above moving averages)
- **Trending Down**: Clear downtrend (ADX > 25, price below moving averages)
- **Ranging/Choppy**: Sideways movement (ADX < 25, low trend strength)
- **High Volatility**: Extreme volatility (ATR > 2x average)

**Gate entries**: Only trade trend-following signals in trending regimes. In ranging/volatile regimes, either:
- Don't trade, OR
- Trade with reduced size and stricter risk limits

### Why Relevant
- **Trend-following fails in ranging markets**: Current bot trades in all conditions
- **Reduces whipsaws**: Avoids losses from false signals in choppy markets
- **Evidence-backed**: Multiple studies show regime-aware strategies outperform

### Expected Benefits
- Higher win rate (fewer false signals)
- Lower drawdowns (avoids bad market conditions)
- Improved Sharpe ratio

### Possible Downsides
- May miss some opportunities (overly conservative)
- Regime classifier may misclassify (adds model risk)

### Implementation Notes
- Add `src/signals/regime_filter.py` module
- Use ADX, volatility, trend strength indicators
- Integrate into `live_bot.py` signal processing
- Add regime confidence threshold to config

---

## 3. Walk-Forward Validation

### Source
- **Prado, M. L. de (2018).** *Advances in Financial Machine Learning*. Chapter 6: "The Dangers of Backtesting".
- **Industry standard** for time-series validation
- **QuantConnect, Zipline** frameworks use walk-forward

### Concept
Instead of random train/test split:
- Use **rolling windows**: Train on 6 months, test on 1 month, roll forward
- Or **expanding windows**: Train on all data up to time T, test on T+1 to T+N
- Prevents look-ahead bias by ensuring model never sees "future" data

### Why Relevant
- **Current issue**: Random split allows model to see future patterns
- **Critical for time-series**: Financial data has temporal dependencies
- **More realistic**: Simulates how model would perform in production

### Expected Benefits
- More realistic performance estimates
- Reduces overfitting risk
- Better model selection

### Possible Downsides
- Less data per fold (smaller training sets)
- More computationally expensive

### Implementation Notes
- Replace `train_test_split()` in `src/models/train.py` with time-based split
- Add walk-forward evaluation module `src/models/evaluation.py`
- Generate performance metrics per fold

---

## 4. Volatility-Targeted Position Sizing

### Source
- **Tharp, V. (1998).** *Trade Your Way to Financial Freedom*. Position sizing chapter.
- **Kelly Criterion** (with fractional Kelly for risk management)
- **Industry practice**: Many quant funds use volatility targeting

### Concept
Adjust position size based on **realized volatility**:
- Calculate recent volatility (e.g., 20-day ATR or rolling std)
- Scale position size inversely with volatility: `size = base_size * (target_vol / current_vol)`
- Target volatility: e.g., 1% daily volatility target

**Rationale**: High volatility = higher risk = smaller positions

### Why Relevant
- **Current issue**: Fixed position size regardless of market conditions
- **Risk parity**: Equalizes risk across different volatility regimes
- **Evidence-backed**: Volatility targeting improves risk-adjusted returns

### Expected Benefits
- More consistent risk exposure
- Lower drawdowns in volatile periods
- Better risk-adjusted returns (higher Sharpe)

### Possible Downsides
- Smaller positions in high volatility (may reduce returns)
- Requires volatility estimation (model risk)

### Implementation Notes
- Modify `calculate_position_size()` in `src/risk/risk_manager.py`
- Add volatility calculation to features
- Add target volatility parameter to config

---

## 5. Performance Guard & Dynamic Risk Throttling

### Source
- **Industry best practices**: Many prop trading firms use performance guards
- **Drawdown-based throttling**: Common in systematic trading
- **Freqtrade** has similar "protections" feature

### Concept
Monitor recent performance and **automatically adjust risk**:
- **Recent PnL**: If last N trades are losing, reduce position size or raise confidence threshold
- **Drawdown-based**: As drawdown increases, reduce risk (smaller positions, higher confidence threshold)
- **Win rate**: If win rate drops below threshold, pause trading or reduce size

**Tiers of throttling**:
1. **Normal**: Full position size, normal confidence threshold
2. **Reduced**: 50% position size, +0.1 confidence threshold
3. **Paused**: Stop trading until performance recovers

### Why Relevant
- **Current issue**: Static risk management doesn't adapt to performance
- **Prevents death spiral**: Stops trading when strategy is failing
- **Self-managing**: Reduces need for manual intervention

### Expected Benefits
- Prevents catastrophic losses during bad periods
- Automatically recovers when performance improves
- More hands-off operation

### Possible Downsides
- May pause trading during temporary drawdowns (miss recoveries)
- Adds complexity

### Implementation Notes
- Create `src/risk/performance_guard.py` module
- Track rolling PnL, win rate, drawdown
- Integrate into `live_bot.py` before trade execution
- Add throttling parameters to config

---

## 6. Funding Rate Integration

### Source
- **Bybit documentation**: Funding rates are critical for perpetual futures
- **Industry practice**: All serious perpetual traders account for funding

### Concept
Include funding rate in:
1. **Label generation**: Subtract funding costs from returns
   - Funding rate: typically 0.01-0.1% per 8 hours
   - For 24h hold: ~0.03-0.3% funding cost
2. **Feature engineering**: Add funding rate as feature
   - High positive funding (longs pay shorts) → bearish signal
   - High negative funding (shorts pay longs) → bullish signal

### Why Relevant
- **Current issue**: Funding not modeled in labels or features
- **Significant cost**: Can erode 0.1-0.3% per day
- **Signal value**: Funding rate reflects market sentiment

### Expected Benefits
- More realistic backtest results
- Better profitability prediction
- Additional signal source

### Possible Downsides
- Requires funding rate data collection
- Adds complexity

### Implementation Notes
- Fetch funding rate from Bybit API
- Include in label calculation in `prepare_data()`
- Add as feature in `build_meta_features()`

---

## 7. Slippage Modeling

### Source
- **Industry standard**: All realistic backtests model slippage
- **QuantConnect, Zipline**: Include slippage models

### Concept
Model slippage in backtests and labels:
- **Market orders**: Add slippage (e.g., 0.01-0.02% for liquid pairs)
- **Volatility-adjusted**: Higher slippage in volatile periods
- **Size-adjusted**: Larger orders = more slippage

**Formula**: `execution_price = close_price * (1 + slippage_factor)`

### Why Relevant
- **Current issue**: Assumes perfect execution at close price
- **Reality**: Market orders fill at worse prices
- **Impact**: Can erode 0.01-0.02% per trade

### Expected Benefits
- More realistic backtest results
- Better alignment with live trading
- More conservative performance estimates

### Possible Downsides
- Slightly lower backtest returns (more realistic)
- Requires slippage estimation

### Implementation Notes
- Add slippage to entry/exit price calculation in `prepare_data()`
- Use volatility to adjust slippage
- Add slippage parameters to config

---

## 8. Portfolio-Level Risk Aggregation

### Source
- **Modern Portfolio Theory**: Diversification and correlation
- **Industry practice**: All multi-symbol strategies aggregate risk

### Concept
When trading multiple symbols (BTC, ETH):
- **Correlation awareness**: BTC and ETH are highly correlated (~0.7-0.9)
- **Portfolio risk**: Aggregate risk across all positions
- **Position limits**: Reduce individual position sizes if portfolio risk is high

**Formula**: `portfolio_risk = sqrt(sum(position_risk^2) + 2 * correlation * position_risk_1 * position_risk_2)`

### Why Relevant
- **Current issue**: Trades symbols independently
- **Reality**: Correlated positions amplify risk
- **Risk management**: Should account for portfolio-level exposure

### Expected Benefits
- More accurate risk assessment
- Prevents over-leveraging across correlated positions
- Better capital allocation

### Possible Downsides
- More complex risk calculation
- Requires correlation estimation

### Implementation Notes
- Add portfolio risk calculation to `risk_manager.py`
- Track correlation between symbols
- Adjust position limits based on portfolio risk

---

## 9. Monte Carlo Resampling

### Source
- **Lopez de Prado, M. (2018).** *Advances in Financial Machine Learning*. Chapter 11: "Backtesting".
- **Industry standard**: Used by quant funds for performance estimation

### Concept
Resample trade sequences to estimate **distribution of returns**:
- Shuffle trade order (maintains individual trade PnL but randomizes sequence)
- Calculate performance metrics (Sharpe, max DD) for each shuffle
- Repeat 1000+ times to get distribution
- Provides confidence intervals on performance

### Why Relevant
- **Current issue**: Single backtest doesn't show performance distribution
- **Uncertainty**: Need to know if results are robust or lucky
- **Risk assessment**: Understand worst-case scenarios

### Expected Benefits
- Confidence intervals on performance
- Better risk assessment
- More robust strategy selection

### Possible Downsides
- Computationally expensive
- May show strategy is less robust than expected

### Implementation Notes
- Add to `src/models/evaluation.py`
- Shuffle trade sequences
- Calculate metrics per shuffle
- Generate distribution plots

---

## 10. Automated Model Retraining & Promotion

### Source
- **MLOps best practices**: Continuous model updates
- **Industry practice**: Quant funds retrain models regularly
- **Freqtrade**: Has model update mechanisms

### Concept
**Automated pipeline**:
1. **Scheduled retraining**: Weekly/monthly retrain on latest data
2. **Validation**: Evaluate new model on hold-out period
3. **Promotion criteria**: Only promote if new model passes thresholds:
   - Sharpe > baseline Sharpe * 0.9 (allow 10% degradation)
   - Max DD < baseline DD * 1.1 (allow 10% worse)
   - Minimum trades (e.g., 50 trades in validation)
4. **Rollback**: Keep previous model for fallback
5. **A/B testing**: Run both models in parallel, compare

### Why Relevant
- **Current issue**: Manual retraining required
- **Model decay**: Models degrade over time as market changes
- **Self-managing**: Reduces operational burden

### Expected Benefits
- Models stay current with market conditions
- Automated quality control
- Hands-off operation

### Possible Downsides
- May promote bad models if validation is flawed
- Requires careful validation design

### Implementation Notes
- Create `scripts/scheduled_retrain.py`
- Add model versioning system
- Implement promotion logic
- Add to cron/scheduler

---

## Priority Ranking

### Tier 1: High-Impact, Low-Risk (Implement First)
1. **Walk-Forward Validation** - Critical fix for overfitting
2. **Slippage Modeling** - Realistic backtests
3. **Funding Rate Integration** - Significant cost, easy to add
4. **Performance Guard** - Prevents catastrophic losses

### Tier 2: Medium Complexity, Solid Evidence
5. **Triple-Barrier Labeling** - Better labels, more realistic
6. **Regime Filter** - Reduces bad trades, evidence-backed
7. **Volatility-Targeted Sizing** - Better risk management

### Tier 3: Advanced / Experimental
8. **Portfolio Risk Aggregation** - Important for multi-symbol
9. **Monte Carlo Resampling** - Advanced evaluation
10. **Automated Retraining** - Operational improvement

---

## References

1. Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
2. Tharp, V. (1998). *Trade Your Way to Financial Freedom*. McGraw-Hill.
3. Freqtrade Documentation: https://www.freqtrade.io/
4. QuantConnect Documentation: https://www.quantconnect.com/docs
5. Bybit API Documentation: https://bybit-exchange.github.io/docs/

---

**Document Date:** December 2025  
**Status:** Ready for Implementation Planning

