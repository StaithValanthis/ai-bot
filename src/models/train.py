"""Model training pipeline"""

import json
import joblib
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Tuple, List
from datetime import datetime
from loguru import logger
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, roc_auc_score, precision_recall_fscore_support
from sklearn.linear_model import LogisticRegression
import xgboost as xgb

from src.signals.features import FeatureCalculator
from src.signals.primary_signal import PrimarySignalGenerator


class EnsembleModel:
    """
    Ensemble model wrapper for XGBoost + Logistic Regression baseline.
    
    This class must be defined at module level for proper joblib serialization.
    """
    def __init__(self, xgb_model, baseline_model, xgb_weight=0.7):
        self.xgb_model = xgb_model
        self.baseline_model = baseline_model
        self.xgb_weight = xgb_weight
    
    def predict_proba(self, X):
        """Predict probability using weighted ensemble"""
        xgb_proba = self.xgb_model.predict_proba(X)[:, 1]
        baseline_proba = self.baseline_model.predict_proba(X)[:, 1]
        ensemble_proba = self.xgb_weight * xgb_proba + (1 - self.xgb_weight) * baseline_proba
        # Return in sklearn format [prob_class_0, prob_class_1]
        return np.column_stack([1 - ensemble_proba, ensemble_proba])


class ModelTrainer:
    """Train meta-model for signal filtering"""
    
    def __init__(self, config: dict):
        """
        Initialize model trainer.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.feature_calc = FeatureCalculator(config)
        self.primary_signal_gen = PrimarySignalGenerator(config)
        self.training_mode = config.get('model', {}).get('training_mode', 'single_symbol')
        self.symbol_encoding_type = config.get('model', {}).get('symbol_encoding', 'one_hot')
        logger.info(f"Initialized ModelTrainer (training_mode={self.training_mode})")
    
    def prepare_data(
        self,
        df: pd.DataFrame,
        symbol: str,
        hold_periods: int = 4,  # Hold for 4 hours (fallback for time barrier)
        profit_threshold: float = 0.005,  # 0.5% profit threshold (fallback)
        fee_rate: float = 0.0005,  # 0.05% per trade
        use_triple_barrier: bool = True,
        profit_barrier: float = 0.02,  # 2% profit barrier
        loss_barrier: float = 0.01,  # 1% loss barrier
        time_barrier_hours: int = 24,  # 24 hour time barrier
        base_slippage: float = 0.0001,  # 0.01% base slippage
        include_funding: bool = True,
        funding_rate: float = 0.0001  # 0.01% per 8 hours (default)
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Prepare training data with labels.
        
        Args:
            df: DataFrame with OHLCV and indicators
            symbol: Trading symbol
            hold_periods: Number of periods to hold position
            profit_threshold: Minimum profit to consider trade successful
            fee_rate: Trading fee rate (per trade)
            
        Returns:
            Tuple of (features_df, labels_series)
        """
        logger.info(f"Preparing training data for {symbol}")
        
        # Calculate indicators
        df = self.feature_calc.calculate_indicators(df)
        
        # Generate labels by simulating trades
        labels = []
        features_list = []
        
        for i in range(len(df) - max(hold_periods, time_barrier_hours) - 1):
            # Get current state
            current_df = df.iloc[:i+1]
            
            # Generate primary signal
            primary_signal = self.primary_signal_gen.generate_signal(current_df)
            
            if primary_signal['direction'] == 'NEUTRAL':
                continue
            
            # Calculate slippage (volatility-adjusted)
            if 'volatility' in current_df.columns and len(current_df) > 20:
                current_vol = current_df['volatility'].iloc[-1]
                avg_vol = current_df['volatility'].rolling(20).mean().iloc[-1]
                vol_factor = current_vol / avg_vol if avg_vol > 0 else 1.0
                slippage = base_slippage * max(vol_factor, 0.5)  # At least 0.5x
            else:
                slippage = base_slippage
            
            # Entry price with slippage
            entry_bar = df.iloc[i+1]
            if primary_signal['direction'] == 'LONG':
                entry_price = entry_bar['close'] * (1 + slippage)
            else:  # SHORT
                entry_price = entry_bar['close'] * (1 - slippage)
            
            # Triple-barrier method
            if use_triple_barrier:
                label, barrier_hit, exit_price, hold_hours = self._triple_barrier_exit(
                    df=df,
                    start_idx=i+1,
                    entry_price=entry_price,
                    direction=primary_signal['direction'],
                    profit_barrier=profit_barrier,
                    loss_barrier=loss_barrier,
                    time_barrier_hours=time_barrier_hours,
                    slippage=slippage
                )
            else:
                # Simple hold-period (backward compatibility)
                exit_bar = df.iloc[i+1+hold_periods]
                if primary_signal['direction'] == 'LONG':
                    exit_price = exit_bar['close'] * (1 - slippage)
                else:
                    exit_price = exit_bar['close'] * (1 + slippage)
                hold_hours = hold_periods
                barrier_hit = "time"
            
            # Calculate return
            if primary_signal['direction'] == 'LONG':
                return_pct = (exit_price - entry_price) / entry_price
            else:  # SHORT
                return_pct = (entry_price - exit_price) / entry_price
            
            # Account for fees and funding
            net_return = return_pct - (2 * fee_rate)  # Entry + exit fees
            
            # Funding cost (perpetual futures)
            if include_funding:
                funding_periods = hold_hours / 8  # Funding every 8 hours
                funding_cost = funding_rate * funding_periods
                net_return -= funding_cost
            
            # Create label (if not using triple-barrier, use threshold)
            if not use_triple_barrier:
                label = 1 if net_return > profit_threshold else 0
            
            # Build features
            features = self.feature_calc.build_meta_features(current_df, primary_signal)
            
            if features:
                features_list.append(features)
                labels.append(label)
        
        if not features_list:
            logger.warning("No training samples generated")
            return pd.DataFrame(), pd.Series(dtype=int)
        
        # Convert to DataFrame
        features_df = pd.DataFrame(features_list)
        labels_series = pd.Series(labels)
        
        logger.info(f"Generated {len(features_df)} training samples (positive: {labels_series.sum()}, negative: {len(labels_series) - labels_series.sum()})")
        
        return features_df, labels_series
    
    def prepare_multi_symbol_data(
        self,
        symbol_dataframes: Dict[str, pd.DataFrame],  # {symbol: df}
        hold_periods: int = 4,
        profit_threshold: float = 0.005,
        fee_rate: float = 0.0005,
        use_triple_barrier: bool = True,
        profit_barrier: float = 0.02,
        loss_barrier: float = 0.01,
        time_barrier_hours: int = 24,
        base_slippage: float = 0.0001,
        include_funding: bool = True,
        funding_rate: float = 0.0001
    ) -> Tuple[pd.DataFrame, pd.Series, Dict[str, List[float]]]:
        """
        Prepare training data from multiple symbols with symbol encoding.
        
        Args:
            symbol_dataframes: Dictionary mapping symbol to DataFrame
            (other args same as prepare_data)
            
        Returns:
            Tuple of (features_df, labels_series, symbol_encoding_map)
            symbol_encoding_map: {symbol: [one_hot_encoding]} for use during live prediction
        """
        logger.info(f"Preparing multi-symbol training data for {len(symbol_dataframes)} symbols")
        
        # Create symbol encoding map
        symbols = sorted(symbol_dataframes.keys())
        symbol_encoding_map = {}
        
        if self.symbol_encoding_type == 'one_hot':
            # One-hot encoding: N symbols -> N-1 features (last symbol is reference)
            for i, sym in enumerate(symbols):
                encoding = [0.0] * (len(symbols) - 1)
                if i < len(symbols) - 1:  # Last symbol is reference (all zeros)
                    encoding[i] = 1.0
                symbol_encoding_map[sym] = encoding
        elif self.symbol_encoding_type == 'index':
            # Simple index encoding: symbol index normalized to [0, 1]
            for i, sym in enumerate(symbols):
                symbol_encoding_map[sym] = [float(i) / max(len(symbols) - 1, 1)]
        else:
            # Default: one-hot
            for i, sym in enumerate(symbols):
                encoding = [0.0] * (len(symbols) - 1)
                if i < len(symbols) - 1:
                    encoding[i] = 1.0
                symbol_encoding_map[sym] = encoding
        
        logger.info(f"Symbol encoding ({self.symbol_encoding_type}): {len(symbol_encoding_map)} symbols, {len(symbol_encoding_map[symbols[0]])} encoding features")
        
        # Prepare data for each symbol
        all_features = []
        all_labels = []
        
        for symbol, df in symbol_dataframes.items():
            logger.info(f"Processing {symbol}: {len(df)} candles")
            
            # Use existing prepare_data method but add symbol encoding
            features_df, labels_series = self.prepare_data(
                df=df,
                symbol=symbol,
                hold_periods=hold_periods,
                profit_threshold=profit_threshold,
                fee_rate=fee_rate,
                use_triple_barrier=use_triple_barrier,
                profit_barrier=profit_barrier,
                loss_barrier=loss_barrier,
                time_barrier_hours=time_barrier_hours,
                base_slippage=base_slippage,
                include_funding=include_funding,
                funding_rate=funding_rate
            )
            
            if features_df.empty:
                logger.warning(f"No training samples for {symbol}, skipping")
                continue
            
            # Add symbol encoding to features
            encoding = symbol_encoding_map[symbol]
            for i, val in enumerate(encoding):
                features_df[f'symbol_id_{i}'] = val
            
            all_features.append(features_df)
            all_labels.append(labels_series)
        
        if not all_features:
            logger.error("No training samples generated from any symbol")
            return pd.DataFrame(), pd.Series(dtype=int), {}
        
        # Combine all features and labels
        combined_features = pd.concat(all_features, ignore_index=True)
        combined_labels = pd.concat(all_labels, ignore_index=True)
        
        logger.info(f"Combined multi-symbol dataset: {len(combined_features)} samples from {len(symbol_dataframes)} symbols")
        logger.info(f"  Positive labels: {combined_labels.sum()}, Negative: {len(combined_labels) - combined_labels.sum()}")
        
        return combined_features, combined_labels, symbol_encoding_map
    
    def _triple_barrier_exit(
        self,
        df: pd.DataFrame,
        start_idx: int,
        entry_price: float,
        direction: str,
        profit_barrier: float,
        loss_barrier: float,
        time_barrier_hours: int,
        slippage: float
    ) -> Tuple[int, str, float, int]:
        """
        Simulate exit using triple-barrier method.
        
        Returns:
            Tuple of (label, barrier_hit, exit_price, hold_hours)
        """
        if direction == 'LONG':
            profit_price = entry_price * (1 + profit_barrier)
            loss_price = entry_price * (1 - loss_barrier)
        else:  # SHORT
            profit_price = entry_price * (1 - profit_barrier)
            loss_price = entry_price * (1 + loss_barrier)
        
        # Get entry time (if available)
        if 'timestamp' in df.columns:
            entry_time = pd.to_datetime(df.iloc[start_idx]['timestamp'])
        else:
            entry_time = None
        
        max_bars = min(time_barrier_hours, len(df) - start_idx - 1)
        
        for j in range(1, max_bars + 1):
            if start_idx + j >= len(df):
                break
            
            bar = df.iloc[start_idx + j]
            
            # Check profit barrier
            if direction == 'LONG':
                if bar['high'] >= profit_price:
                    exit_price = profit_price * (1 - slippage)  # Exit with slippage
                    return 1, "profit", exit_price, j
                elif bar['low'] <= loss_price:
                    exit_price = loss_price * (1 - slippage)
                    return 0, "loss", exit_price, j
            else:  # SHORT
                if bar['low'] <= profit_price:
                    exit_price = profit_price * (1 + slippage)
                    return 1, "profit", exit_price, j
                elif bar['high'] >= loss_price:
                    exit_price = loss_price * (1 + slippage)
                    return 0, "loss", exit_price, j
            
            # Check time barrier (if timestamps available)
            if entry_time is not None and 'timestamp' in df.columns:
                try:
                    bar_time = pd.to_datetime(bar['timestamp'])
                    if isinstance(bar_time, pd.Timestamp) and isinstance(entry_time, pd.Timestamp):
                        hours_elapsed = (bar_time - entry_time).total_seconds() / 3600
                        if hours_elapsed >= time_barrier_hours:
                            exit_price = bar['close'] * (1 - slippage if direction == 'LONG' else 1 + slippage)
                            return 0, "time", exit_price, int(hours_elapsed)
                except:
                    pass  # Fall back to bar count
        
        # Time barrier hit (reached max bars)
        last_bar = df.iloc[start_idx + max_bars]
        exit_price = last_bar['close'] * (1 - slippage if direction == 'LONG' else 1 + slippage)
        return 0, "time", exit_price, max_bars
    
    def train_model(
        self,
        features_df: pd.DataFrame,
        labels: pd.Series,
        test_size: float = 0.2,
        validation_size: float = 0.2,
        use_ensemble: bool = True
    ) -> Tuple[any, StandardScaler, Dict]:
        """
        Train meta-model.
        
        Args:
            features_df: Feature DataFrame
            labels: Binary labels
            test_size: Fraction of data for testing
            validation_size: Fraction of remaining data for validation
            
        Returns:
            Tuple of (trained_model, scaler, metrics_dict)
        """
        logger.info("Training meta-model")
        
        # Time-based split (critical for time-series data)
        # Use first 60% for training, next 20% for validation, last 20% for test
        total_size = len(features_df)
        train_end = int(total_size * (1 - test_size - validation_size))
        val_end = int(total_size * (1 - test_size))
        
        X_train = features_df.iloc[:train_end]
        y_train = labels.iloc[:train_end]
        
        X_val = features_df.iloc[train_end:val_end]
        y_val = labels.iloc[train_end:val_end]
        
        X_test = features_df.iloc[val_end:]
        y_test = labels.iloc[val_end:]
        
        logger.info(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)
        X_test_scaled = scaler.transform(X_test)
        
        # Train XGBoost model
        xgb_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric='logloss'
        )
        
        xgb_model.fit(
            X_train_scaled,
            y_train,
            eval_set=[(X_val_scaled, y_val)],
            early_stopping_rounds=10,  # Must be passed to fit() to function properly
            verbose=False
        )
        
        # Evaluate XGBoost
        xgb_pred = xgb_model.predict(X_test_scaled)
        xgb_pred_proba = xgb_model.predict_proba(X_test_scaled)[:, 1]
        
        xgb_precision, xgb_recall, xgb_f1, _ = precision_recall_fscore_support(y_test, xgb_pred, average='binary', zero_division=0)
        xgb_auc = roc_auc_score(y_test, xgb_pred_proba)
        
        metrics = {
            'xgb_precision': float(xgb_precision),
            'xgb_recall': float(xgb_recall),
            'xgb_f1_score': float(xgb_f1),
            'xgb_roc_auc': float(xgb_auc),
            'test_samples': len(X_test),
            'positive_rate': float(y_test.mean())
        }
        
        logger.info(f"XGBoost performance - Precision: {xgb_precision:.3f}, Recall: {xgb_recall:.3f}, F1: {xgb_f1:.3f}, AUC: {xgb_auc:.3f}")
        
        # Train baseline model (Logistic Regression) if ensemble enabled
        baseline_model = None
        if use_ensemble:
            logger.info("Training baseline model (Logistic Regression)")
            baseline_model = LogisticRegression(
                max_iter=1000,
                random_state=42,
                class_weight='balanced'
            )
            
            baseline_model.fit(X_train_scaled, y_train)
            
            # Evaluate baseline
            baseline_pred = baseline_model.predict(X_test_scaled)
            baseline_pred_proba = baseline_model.predict_proba(X_test_scaled)[:, 1]
            
            baseline_precision, baseline_recall, baseline_f1, _ = precision_recall_fscore_support(y_test, baseline_pred, average='binary', zero_division=0)
            baseline_auc = roc_auc_score(y_test, baseline_pred_proba)
            
            metrics.update({
                'baseline_precision': float(baseline_precision),
                'baseline_recall': float(baseline_recall),
                'baseline_f1_score': float(baseline_f1),
                'baseline_roc_auc': float(baseline_auc)
            })
            
            logger.info(f"Baseline performance - Precision: {baseline_precision:.3f}, Recall: {baseline_recall:.3f}, F1: {baseline_f1:.3f}, AUC: {baseline_auc:.3f}")
            
            # Create ensemble model wrapper (using module-level class for proper serialization)
            ensemble_weight = self.config.get('model', {}).get('ensemble_xgb_weight', 0.7)
            model = EnsembleModel(xgb_model, baseline_model, xgb_weight=ensemble_weight)
            
            # Evaluate ensemble
            ensemble_pred_proba = model.predict_proba(X_test_scaled)[:, 1]
            ensemble_pred = (ensemble_pred_proba > 0.5).astype(int)
            
            ensemble_precision, ensemble_recall, ensemble_f1, _ = precision_recall_fscore_support(y_test, ensemble_pred, average='binary', zero_division=0)
            ensemble_auc = roc_auc_score(y_test, ensemble_pred_proba)
            
            metrics.update({
                'ensemble_precision': float(ensemble_precision),
                'ensemble_recall': float(ensemble_recall),
                'ensemble_f1_score': float(ensemble_f1),
                'ensemble_roc_auc': float(ensemble_auc)
            })
            
            logger.info(f"Ensemble performance - Precision: {ensemble_precision:.3f}, Recall: {ensemble_recall:.3f}, F1: {ensemble_f1:.3f}, AUC: {ensemble_auc:.3f}")
        else:
            model = xgb_model
        
        return model, scaler, metrics
    
    def save_model(
        self,
        model: any,
        scaler: StandardScaler,
        metrics: Dict,
        features_df: pd.DataFrame,
        version: str = "1.0"
    ):
        """
        Save trained model and artifacts.
        
        Args:
            model: Trained XGBoost model
            scaler: Feature scaler
            metrics: Performance metrics
            features_df: Feature DataFrame (for feature names)
            version: Model version
        """
        model_dir = Path("models")
        model_dir.mkdir(exist_ok=True)
        
        # Save model
        model_path = model_dir / f"meta_model_v{version}.joblib"
        joblib.dump(model, model_path)
        logger.info(f"Saved model to {model_path}")
        
        # Save scaler
        scaler_path = model_dir / f"feature_scaler_v{version}.joblib"
        joblib.dump(scaler, scaler_path)
        logger.info(f"Saved scaler to {scaler_path}")
        
        # Save config with model coverage metadata
        config = {
            'version': version,
            'training_date': datetime.utcnow().isoformat(),
            'features': list(features_df.columns),
            'performance': metrics,
            'training_mode': self.training_mode,
            'symbol_encoding_type': self.symbol_encoding_type
        }
        
        # Add model coverage metadata
        if hasattr(self, 'trained_symbols') and self.trained_symbols:
            config['trained_symbols'] = self.trained_symbols
            logger.info(f"Saved trained_symbols: {self.trained_symbols}")
        
        if hasattr(self, 'training_days') and self.training_days:
            config['training_days'] = self.training_days
        
        if hasattr(self, 'training_end_timestamp') and self.training_end_timestamp:
            config['training_end_timestamp'] = self.training_end_timestamp.isoformat() if hasattr(self.training_end_timestamp, 'isoformat') else str(self.training_end_timestamp)
        
        if hasattr(self, 'min_history_days_per_symbol') and self.min_history_days_per_symbol:
            config['min_history_days_per_symbol'] = self.min_history_days_per_symbol
        
        # Add per-symbol history days if available (for multi-symbol models)
        if hasattr(self, 'symbol_history_days') and self.symbol_history_days:
            config['symbol_history_days'] = self.symbol_history_days
            logger.info(f"Saved per-symbol history days: {self.symbol_history_days}")
        
        # Add symbol encoding map if multi-symbol training
        if hasattr(self, 'symbol_encoding_map') and self.symbol_encoding_map:
            config['symbol_encoding_map'] = self.symbol_encoding_map
            logger.info(f"Saved symbol encoding map for {len(self.symbol_encoding_map)} symbols")
        
        config_path = model_dir / f"model_config_v{version}.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Saved config to {config_path}")

