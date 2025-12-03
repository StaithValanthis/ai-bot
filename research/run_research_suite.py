#!/usr/bin/env python3
"""
Automated research and evaluation harness.

Runs walk-forward backtests on multiple symbols and configurations to evaluate
strategy robustness and identify promising parameter sets.

Usage:
    python research/run_research_suite.py --symbols BTCUSDT ETHUSDT --years 2
"""

import argparse
import sys
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from itertools import product
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.config_loader import load_config
from src.data.historical_data import HistoricalDataCollector
from src.models.train import ModelTrainer
from src.models.evaluation import (
    walk_forward_validation,
    aggregate_walk_forward_results,
    calculate_metrics
)
from src.signals.features import FeatureCalculator
from src.signals.primary_signal import PrimarySignalGenerator
from src.signals.regime_filter import RegimeFilter
from src.portfolio.selector import PortfolioSelector
from src.signals.meta_predictor import MetaPredictor
from src.exchange.universe import UniverseManager


class ResearchHarness:
    """Automated research and evaluation harness"""
    
    def __init__(self, base_config: dict):
        """
        Initialize research harness.
        
        Args:
            base_config: Base configuration dictionary
        """
        self.base_config = base_config
        self.results = []
        logger.info("Initialized ResearchHarness")
    
    def generate_config_variants(
        self,
        risk_levels: List[str] = ["conservative", "moderate", "aggressive"],
        ensemble_options: List[bool] = [True, False],
        portfolio_options: List[bool] = [False, True],
        regime_sensitivity: List[str] = ["strict", "moderate", "lenient"],
        barrier_params: List[dict] = None
    ) -> List[dict]:
        """
        Generate configuration variants for testing.
        
        Args:
            risk_levels: List of risk level names
            ensemble_options: List of ensemble on/off options
            portfolio_options: List of portfolio layer on/off options
            regime_sensitivity: List of regime filter sensitivity levels
            barrier_params: List of triple-barrier parameter dicts (or None for default)
            
        Returns:
            List of configuration dictionaries
        """
        variants = []
        base = self.base_config.copy()
        
        # Default barrier params if not provided
        if barrier_params is None:
            barrier_params = [
                {"profit_barrier": 0.02, "loss_barrier": 0.01, "time_barrier_hours": 24}  # Default
            ]
        
        risk_configs = {
            "conservative": {
                "max_leverage": 2.0,
                "base_position_size": 0.01,  # 1%
                "max_position_size": 0.05,  # 5%
                "confidence_threshold": 0.65,
                "regime_filter": {"adx_threshold": 30, "allow_ranging": False},
                "volatility_targeting": {"target_volatility": 0.008},  # 0.8% daily
                "performance_guard": {
                    "win_rate_threshold_reduced": 0.35,
                    "win_rate_threshold_paused": 0.25
                }
            },
            "moderate": {
                "max_leverage": 3.0,
                "base_position_size": 0.02,  # 2%
                "max_position_size": 0.10,  # 10%
                "confidence_threshold": 0.60,
                "regime_filter": {"adx_threshold": 25, "allow_ranging": False},
                "volatility_targeting": {"target_volatility": 0.01},  # 1% daily
                "performance_guard": {
                    "win_rate_threshold_reduced": 0.40,
                    "win_rate_threshold_paused": 0.30
                }
            },
            "aggressive": {
                "max_leverage": 5.0,
                "base_position_size": 0.03,  # 3%
                "max_position_size": 0.15,  # 15%
                "confidence_threshold": 0.55,
                "regime_filter": {"adx_threshold": 20, "allow_ranging": True},
                "volatility_targeting": {"target_volatility": 0.015},  # 1.5% daily
                "performance_guard": {
                    "win_rate_threshold_reduced": 0.45,
                    "win_rate_threshold_paused": 0.35
                }
            }
        }
        
        regime_adx_map = {
            "strict": 30,
            "moderate": 25,
            "lenient": 20
        }
        
        # Generate all combinations
        for risk_level, use_ensemble, use_portfolio, regime_sens, barriers in product(
            risk_levels, ensemble_options, portfolio_options, regime_sensitivity, barrier_params
        ):
            variant = base.copy()
            risk_config = risk_configs.get(risk_level, risk_configs["moderate"])
            
            # Update risk settings
            if "risk" not in variant:
                variant["risk"] = {}
            variant["risk"].update({
                "max_leverage": risk_config["max_leverage"],
                "base_position_size": risk_config["base_position_size"],
                "max_position_size": risk_config["max_position_size"]
            })
            
            # Update model settings
            if "model" not in variant:
                variant["model"] = {}
            variant["model"]["confidence_threshold"] = risk_config["confidence_threshold"]
            variant["model"]["use_ensemble"] = use_ensemble
            variant["model"]["ensemble_models"] = use_ensemble  # Alias for compatibility
            
            # Update regime filter (override with sensitivity level)
            if "regime_filter" not in variant:
                variant["regime_filter"] = {}
            variant["regime_filter"].update({
                "adx_threshold": regime_adx_map.get(regime_sens, 25),
                "allow_ranging": (regime_sens == "lenient")
            })
            
            # Update volatility targeting
            if "volatility_targeting" not in variant:
                variant["volatility_targeting"] = {}
            variant["volatility_targeting"].update(risk_config["volatility_targeting"])
            
            # Update performance guard
            if "performance_guard" not in variant:
                variant["performance_guard"] = {}
            variant["performance_guard"].update(risk_config["performance_guard"])
            
            # Update portfolio layer
            if "portfolio" not in variant:
                variant["portfolio"] = {}
            if "cross_sectional" not in variant["portfolio"]:
                variant["portfolio"]["cross_sectional"] = {}
            variant["portfolio"]["cross_sectional"]["enabled"] = use_portfolio
            if use_portfolio:
                variant["portfolio"]["cross_sectional"].update({
                    "top_k": 3,
                    "rebalance_interval_minutes": 1440
                })
            
            # Update labeling (triple-barrier)
            if "labeling" not in variant:
                variant["labeling"] = {}
            variant["labeling"].update({
                "use_triple_barrier": True,
                "profit_barrier": barriers["profit_barrier"],
                "loss_barrier": barriers["loss_barrier"],
                "time_barrier_hours": barriers["time_barrier_hours"]
            })
            
            # Create human-readable config ID
            config_id = f"{risk_level}_ens{use_ensemble}_port{use_portfolio}_reg{regime_sens}_bar{barriers['profit_barrier']:.2f}"
            
            variant["_research_metadata"] = {
                "risk_level": risk_level,
                "use_ensemble": use_ensemble,
                "use_portfolio": use_portfolio,
                "regime_sensitivity": regime_sens,
                "barrier_params": barriers,
                "variant_id": config_id
            }
            
            variants.append(variant)
        
        logger.info(f"Generated {len(variants)} configuration variants")
        return variants
    
    def backtest_configuration(
        self,
        config: dict,
        symbol: str,
        data: pd.DataFrame,
        train_window_days: int = 180,
        test_window_days: int = 30,
        step_days: int = 30
    ) -> Dict[str, any]:
        """
        Backtest a configuration using walk-forward validation.
        
        Args:
            config: Configuration dictionary
            symbol: Trading symbol
            data: Historical OHLCV data
            train_window_days: Training window size
            test_window_days: Test window size
            step_days: Step size for rolling forward
            
        Returns:
            Dictionary with backtest results
        """
        logger.info(f"Backtesting {symbol} with config variant: {config.get('_research_metadata', {}).get('variant_id', 'unknown')}")
        
        # Initialize components
        feature_calc = FeatureCalculator(config)
        primary_signal_gen = PrimarySignalGenerator(config)
        regime_filter = RegimeFilter(config)
        portfolio_selector = PortfolioSelector(config)
        
        # Prepare data
        df = feature_calc.calculate_indicators(data.copy())
        
        # Define training function
        def train_func(train_data: pd.DataFrame):
            trainer = ModelTrainer(config)
            
            # Prepare training data
            labeling_config = config.get('labeling', {})
            execution_config = config.get('execution', {})
            
            features_df, labels = trainer.prepare_data(
                df=train_data,
                symbol=symbol,
                hold_periods=4,
                profit_threshold=0.005,
                fee_rate=0.0005,
                use_triple_barrier=labeling_config.get('use_triple_barrier', True),
                profit_barrier=labeling_config.get('profit_barrier', 0.02),
                loss_barrier=labeling_config.get('loss_barrier', 0.01),
                time_barrier_hours=labeling_config.get('time_barrier_hours', 24),
                base_slippage=execution_config.get('base_slippage', 0.0001),
                include_funding=execution_config.get('include_funding', True),
                funding_rate=execution_config.get('default_funding_rate', 0.0001)
            )
            
            if features_df.empty:
                return None
            
            # Train model
            model, scaler, metrics = trainer.train_model(
                features_df=features_df,
                labels=labels,
                test_size=0.2,
                validation_size=0.2
            )
            
            return {
                'model': model,
                'scaler': scaler,
                'feature_calc': feature_calc,
                'primary_signal_gen': primary_signal_gen,
                'config': config
            }
        
        # Define test function
        def test_func(model_dict: dict, test_data: pd.DataFrame) -> Dict[str, float]:
            if model_dict is None:
                return {
                    'total_return': 0.0,
                    'sharpe_ratio': 0.0,
                    'profit_factor': 0.0,
                    'max_drawdown': 0.0,
                    'win_rate': 0.0,
                    'total_trades': 0
                }
            
            model = model_dict['model']
            scaler = model_dict['scaler']
            feature_calc = model_dict['feature_calc']
            primary_signal_gen = model_dict['primary_signal_gen']
            config = model_dict['config']
            
            # Simulate trading on test data
            trades = []
            initial_equity = 10000.0
            equity = initial_equity
            
            # Calculate features for test period
            test_df = feature_calc.calculate_indicators(test_data.copy())
            
            # Simulate trades
            for i in range(len(test_df) - 24):  # Need some lookahead
                current_df = test_df.iloc[:i+1]
                
                # Generate signal
                primary_signal = primary_signal_gen.generate_signal(current_df)
                if primary_signal['direction'] == 'NEUTRAL':
                    continue
                
                # Regime filter check
                regime_allowed, regime_reason, regime_multiplier = regime_filter.should_allow_trade(
                    current_df, primary_signal['direction']
                )
                if not regime_allowed:
                    continue
                
                # Portfolio selector check (if enabled)
                if portfolio_selector.enabled:
                    # For backtesting, we'll allow all symbols (portfolio selection is more relevant for live)
                    # But we could implement selection logic here if needed
                    pass
                
                # Build features
                meta_features = feature_calc.build_meta_features(current_df, primary_signal)
                if not meta_features:
                    continue
                
                # Predict
                feature_array = np.array([list(meta_features.values())]).reshape(1, -1)
                feature_array_scaled = scaler.transform(feature_array)
                confidence = model.predict_proba(feature_array_scaled)[0, 1]
                
                # Check confidence threshold
                threshold = config['model']['confidence_threshold']
                if confidence < threshold:
                    continue
                
                # Simulate trade
                entry_price = test_df.iloc[i+1]['close']
                exit_idx = min(i + 24, len(test_df) - 1)  # Hold for up to 24 hours
                exit_price = test_df.iloc[exit_idx]['close']
                
                # Calculate PnL
                if primary_signal['direction'] == 'LONG':
                    return_pct = (exit_price - entry_price) / entry_price
                else:
                    return_pct = (entry_price - exit_price) / entry_price
                
                # Account for costs
                fee_rate = 0.0005
                slippage = 0.0001
                funding_cost = 0.0001 * 3  # 24h = 3 funding periods
                net_return = return_pct - (2 * fee_rate) - (2 * slippage) - funding_cost
                
                pnl = equity * 0.02 * confidence * net_return  # Simplified position sizing
                equity += pnl
                
                trades.append({
                    'entry_time': test_df.iloc[i+1].get('timestamp', i),
                    'exit_time': test_df.iloc[exit_idx].get('timestamp', exit_idx),
                    'pnl': pnl,
                    'direction': primary_signal['direction'],
                    'confidence': confidence
                })
            
            if len(trades) == 0:
                return {
                    'total_return': 0.0,
                    'sharpe_ratio': 0.0,
                    'profit_factor': 0.0,
                    'max_drawdown': 0.0,
                    'win_rate': 0.0,
                    'total_trades': 0
                }
            
            # Calculate metrics
            trades_df = pd.DataFrame(trades)
            metrics = calculate_metrics(trades_df, initial_equity)
            
            return metrics
        
        # Run walk-forward validation
        try:
            results = walk_forward_validation(
                data=df,
                train_func=train_func,
                test_func=test_func,
                train_window_days=train_window_days,
                test_window_days=test_window_days,
                step_days=step_days
            )
            
            if not results:
                logger.warning(f"No results for {symbol}")
                return {}
            
            # Aggregate results
            aggregated = aggregate_walk_forward_results(results)
            
            # Add metadata
            aggregated['symbol'] = symbol
            aggregated['config_variant'] = config.get('_research_metadata', {}).get('variant_id', 'unknown')
            aggregated['risk_level'] = config.get('_research_metadata', {}).get('risk_level', 'unknown')
            aggregated['num_folds'] = len(results)
            
            return aggregated
        
        except Exception as e:
            logger.error(f"Error backtesting {symbol}: {e}")
            return {
                'symbol': symbol,
                'error': str(e),
                'config_variant': config.get('_research_metadata', {}).get('variant_id', 'unknown')
            }
    
    def run_research_suite(
        self,
        symbols: List[str],
        years: int = 2,
        risk_levels: List[str] = ["conservative", "moderate", "aggressive"],
        ensemble_options: List[bool] = [True, False],
        portfolio_options: List[bool] = [False, True],
        regime_sensitivity: List[str] = ["strict", "moderate", "lenient"],
        output_dir: str = "research_results"
    ) -> pd.DataFrame:
        """
        Run full research suite.
        
        Args:
            symbols: List of symbols to test
            years: Years of history to use
            risk_levels: Risk levels to test
            
        Returns:
            DataFrame with all results
        """
        logger.info(f"Starting research suite: {len(symbols)} symbols, {years} years")
        logger.info(f"Risk levels: {risk_levels}, Ensemble: {ensemble_options}, Portfolio: {portfolio_options}")
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Generate config variants
        config_variants = self.generate_config_variants(
            risk_levels=risk_levels,
            ensemble_options=ensemble_options,
            portfolio_options=portfolio_options,
            regime_sensitivity=regime_sensitivity,
            barrier_params=None  # Use defaults
        )
        
        # Initialize data collector
        data_collector = HistoricalDataCollector(
            api_key=self.base_config['exchange'].get('api_key'),
            api_secret=self.base_config['exchange'].get('api_secret'),
            testnet=self.base_config['exchange'].get('testnet', True)
        )
        
        all_results = []
        
        # Test each symbol and config combination
        for symbol in symbols:
            logger.info(f"Processing {symbol}...")
            
            # Download or load data
            data_path = self.base_config.get('data', {}).get('historical_data_path', 'data/raw/bybit')
            data = data_collector.load_candles(
                symbol=symbol,
                timeframe="60",
                data_path=data_path
            )
            
            if data.empty:
                logger.warning(f"No data for {symbol}, downloading...")
                data = data_collector.download_and_save(
                    symbol=symbol,
                    days=years * 365,
                    interval="60",
                    data_path=data_path
                )
            
            if data.empty:
                logger.error(f"Could not get data for {symbol}")
                continue
            
            # Run quality checks if enabled
            if self.base_config.get('data', {}).get('data_quality_checks_enabled', True):
                from src.data.quality_checks import DataQualityChecker
                quality_checker = DataQualityChecker(expected_interval_minutes=60)
                quality_results = quality_checker.check_dataframe(data, symbol, "60")
                
                if not quality_results['passed']:
                    logger.warning(f"Data quality issues for {symbol}: {quality_results['issues']}")
                    # Continue anyway, but log the issues
            
            # Filter to requested years
            if 'timestamp' in data.columns:
                cutoff_date = data['timestamp'].max() - timedelta(days=years * 365)
                data = data[data['timestamp'] >= cutoff_date].copy()
                
                if data.empty:
                    logger.error(f"After filtering to {years} years, no data remains for {symbol}")
                    continue
            
            # Test each config variant
            for config in config_variants:
                result = self.backtest_configuration(
                    config=config,
                    symbol=symbol,
                    data=data
                )
                
                if result:
                    all_results.append(result)
                    
                    # Save individual result
                    config_id = result.get('config_variant', 'unknown')
                    result_file = output_path / f"{symbol}_{config_id}_result.json"
                    with open(result_file, 'w') as f:
                        json.dump(result, f, indent=2, default=str)
        
        # Convert to DataFrame
        if all_results:
            results_df = pd.DataFrame(all_results)
            
            # Save aggregated CSV
            csv_path = output_path / "all_results.csv"
            results_df.to_csv(csv_path, index=False)
            logger.info(f"Saved {len(results_df)} results to {csv_path}")
            
            return results_df
        else:
            logger.warning("No results generated")
            return pd.DataFrame()
    
    def generate_report(self, results_df: pd.DataFrame, output_path: str = "docs/PHASE8_RESEARCH_SUMMARY.md"):
        """
        Generate research summary report.
        
        Args:
            results_df: DataFrame with backtest results
            output_path: Path to save report
        """
        if results_df.empty:
            logger.warning("No results to report")
            return
        
        report_lines = [
            "# Phase 8: Research Suite Summary",
            "",
            f"**Generated:** {datetime.utcnow().isoformat()}",
            "",
            "## Overview",
            "",
            f"Total configurations tested: {len(results_df)}",
            f"Symbols tested: {', '.join(results_df['symbol'].unique()) if 'symbol' in results_df.columns else 'N/A'}",
            "",
            "## Results by Symbol and Risk Level",
            ""
        ]
        
        # Group by symbol and risk level
        if 'symbol' in results_df.columns and 'risk_level' in results_df.columns:
            for symbol in results_df['symbol'].unique():
                report_lines.append(f"### {symbol}")
                report_lines.append("")
                
                symbol_data = results_df[results_df['symbol'] == symbol]
                
                for risk_level in symbol_data['risk_level'].unique():
                    risk_data = symbol_data[symbol_data['risk_level'] == risk_level]
                    
                    if len(risk_data) > 0:
                        row = risk_data.iloc[0]
                        report_lines.append(f"#### {risk_level.upper()}")
                        report_lines.append("")
                        report_lines.append(f"- **Sharpe Ratio:** {row.get('sharpe_ratio_mean', 0):.2f} ± {row.get('sharpe_ratio_std', 0):.2f}")
                        report_lines.append(f"- **Profit Factor:** {row.get('profit_factor_mean', 0):.2f} ± {row.get('profit_factor_std', 0):.2f}")
                        report_lines.append(f"- **Max Drawdown:** {row.get('max_drawdown_mean', 0):.2%} ± {row.get('max_drawdown_std', 0):.2%}")
                        report_lines.append(f"- **Win Rate:** {row.get('win_rate_mean', 0):.2%} ± {row.get('win_rate_std', 0):.2%}")
                        report_lines.append(f"- **Total Trades:** {row.get('total_trades', 0)}")
                        report_lines.append(f"- **Number of Folds:** {row.get('num_folds', 0)}")
                        report_lines.append("")
        
        # Top configurations
        report_lines.extend([
            "## Top Configurations (by Sharpe Ratio)",
            ""
        ])
        
        if 'sharpe_ratio_mean' in results_df.columns:
            top_configs = results_df.nlargest(5, 'sharpe_ratio_mean')
            for idx, row in top_configs.iterrows():
                report_lines.append(f"### {row.get('symbol', 'Unknown')} - {row.get('risk_level', 'Unknown')}")
                report_lines.append(f"- Sharpe: {row.get('sharpe_ratio_mean', 0):.2f}")
                report_lines.append(f"- Profit Factor: {row.get('profit_factor_mean', 0):.2f}")
                report_lines.append(f"- Max DD: {row.get('max_drawdown_mean', 0):.2%}")
                report_lines.append("")
        
        # Stability analysis
        report_lines.extend([
            "## Stability Analysis",
            "",
            "### Fragility Indicators",
            ""
        ])
        
        if 'sharpe_ratio_std' in results_df.columns and 'sharpe_ratio_mean' in results_df.columns:
            results_df['sharpe_cv'] = results_df['sharpe_ratio_std'] / (results_df['sharpe_ratio_mean'] + 1e-10)
            fragile = results_df[results_df['sharpe_cv'] > 0.5]  # High coefficient of variation
            
            if len(fragile) > 0:
                report_lines.append("**High Fragility (CV > 0.5):**")
                for idx, row in fragile.iterrows():
                    report_lines.append(f"- {row.get('symbol', 'Unknown')} - {row.get('risk_level', 'Unknown')}: CV = {row['sharpe_cv']:.2f}")
            else:
                report_lines.append("No high-fragility configurations detected.")
        
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("**Note:** These results are from backtesting and do not guarantee future performance.")
        
        # Write report
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            f.write('\n'.join(report_lines))
        
        logger.info(f"Report saved to {output_file}")
        
        # Also save raw results as CSV
        csv_path = output_file.parent / "PHASE8_RESEARCH_RESULTS.csv"
        results_df.to_csv(csv_path, index=False)
        logger.info(f"Raw results saved to {csv_path}")


def main():
    parser = argparse.ArgumentParser(description='Run research suite')
    parser.add_argument('--symbols', nargs='+', default=None, help='Symbols to test (if not provided, uses universe or config)')
    parser.add_argument('--years', type=int, default=2, help='Years of history')
    parser.add_argument('--risk-levels', nargs='+', default=['conservative', 'moderate'], help='Risk levels')
    parser.add_argument('--ensemble', nargs='+', type=str, default=['true', 'false'], help='Ensemble on/off (true/false)')
    parser.add_argument('--portfolio', nargs='+', type=str, default=['false'], help='Portfolio layer on/off (true/false)')
    parser.add_argument('--regime', nargs='+', default=['moderate'], help='Regime sensitivity (strict/moderate/lenient)')
    parser.add_argument('--config', type=str, default='config/config.yaml', help='Config file')
    parser.add_argument('--output-dir', type=str, default='research_results', help='Output directory')
    parser.add_argument('--quick', action='store_true', help='Quick test (BTCUSDT only, conservative, ensemble on)')
    
    args = parser.parse_args()
    
    # Quick test mode
    if args.quick:
        args.symbols = ['BTCUSDT']
        args.risk_levels = ['conservative']
        args.ensemble = ['true']
        args.portfolio = ['false']
        args.regime = ['moderate']
        args.years = 1  # Shorter for quick test
        logger.info("Quick test mode enabled")
    
    # Configure logging
    logger.add("logs/research_{time}.log", rotation="1 day", level="INFO")
    
    logger.info("=" * 60)
    logger.info("Starting Research Suite")
    logger.info("=" * 60)
    
    # Load config
    config = load_config(args.config)
    
    # Determine symbols to test
    if args.symbols:
        symbols = args.symbols
        logger.info(f"Using explicit symbols: {symbols}")
    else:
        # Use universe manager or fallback to config
        universe_manager = UniverseManager(config)
        symbols = universe_manager.get_symbols()
        if not symbols:
            # Fallback to config symbols
            symbols = config.get('trading', {}).get('symbols', ['BTCUSDT', 'ETHUSDT'])
        
        # Limit to top N for research (to keep runs reasonable)
        max_research_symbols = config.get('exchange', {}).get('max_symbols', 30)
        if len(symbols) > max_research_symbols:
            logger.info(f"Limiting research to top {max_research_symbols} symbols by liquidity")
            symbols = symbols[:max_research_symbols]
        
        logger.info(f"Using {len(symbols)} symbols from universe/config: {symbols[:10]}{'...' if len(symbols) > 10 else ''}")
    
    # Initialize harness
    harness = ResearchHarness(config)
    
    # Parse boolean arguments
    ensemble_options = [e.lower() == 'true' for e in args.ensemble]
    portfolio_options = [p.lower() == 'true' for p in args.portfolio]
    
    # Run research suite
    results_df = harness.run_research_suite(
        symbols=symbols,
        years=args.years,
        risk_levels=args.risk_levels,
        ensemble_options=ensemble_options,
        portfolio_options=portfolio_options,
        regime_sensitivity=args.regime,
        output_dir=args.output_dir
    )
    
    # Generate report
    if not results_df.empty:
        report_path = Path(args.output_dir) / "PHASE17_EXPERIMENT_RESULTS.md"
        harness.generate_report(results_df, output_path=str(report_path))
        logger.info(f"Research suite completed: {len(results_df)} configurations tested")
        logger.info(f"Results saved to {args.output_dir}/")
        logger.info(f"Report saved to {report_path}")
    else:
        logger.error("No results generated")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

