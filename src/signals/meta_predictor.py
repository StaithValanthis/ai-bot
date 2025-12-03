"""Meta-model prediction for signal filtering"""

import json
import joblib
import numpy as np
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
from loguru import logger
from sklearn.preprocessing import StandardScaler


class MetaPredictor:
    """Predict profitability probability of primary signals using meta-model"""
    
    def __init__(
        self,
        model_path: str,
        scaler_path: str,
        config_path: Optional[str] = None
    ):
        """
        Initialize meta-model predictor.
        
        Args:
            model_path: Path to trained XGBoost model (joblib)
            scaler_path: Path to feature scaler (joblib)
            config_path: Path to model config JSON (optional)
        """
        self.model_path = Path(model_path)
        self.scaler_path = Path(scaler_path)
        self.config_path = Path(config_path) if config_path else None
        
        self.model = None
        self.scaler = None
        self.feature_names = None
        self.config = {}
        
        self._load_model()
        logger.info(f"Loaded meta-model from {model_path}")
    
    def _load_model(self):
        """Load model, scaler, and config"""
        try:
            # Load model
            if not self.model_path.exists():
                raise FileNotFoundError(f"Model file not found: {self.model_path}")
            self.model = joblib.load(self.model_path)
            
            # Load scaler
            if not self.scaler_path.exists():
                raise FileNotFoundError(f"Scaler file not found: {self.scaler_path}")
            self.scaler = joblib.load(self.scaler_path)
            
            # Load config if available
            if self.config_path and self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
                self.feature_names = self.config.get('features', [])
                # Store symbol encoding map if available (for multi-symbol models)
                if 'symbol_encoding_map' in self.config:
                    logger.info(f"Loaded symbol encoding map for {len(self.config['symbol_encoding_map'])} symbols")
            
            logger.info("Successfully loaded meta-model components")
            
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise
    
    @property
    def trained_symbols(self) -> List[str]:
        """Get list of symbols used in training"""
        symbols = self.config.get('trained_symbols', [])
        if not symbols:
            logger.warning("Model config missing 'trained_symbols' metadata (older model?)")
        return symbols if isinstance(symbols, list) else []
    
    @property
    def training_days(self) -> int:
        """Get number of days of history used in training"""
        days = self.config.get('training_days', 0)
        if days == 0:
            logger.warning("Model config missing 'training_days' metadata (older model?)")
        return days
    
    @property
    def training_mode(self) -> str:
        """Get training mode: 'single_symbol' or 'multi_symbol'"""
        return self.config.get('training_mode', 'single_symbol')
    
    @property
    def training_end_timestamp(self) -> Optional[str]:
        """Get last timestamp in training data"""
        return self.config.get('training_end_timestamp', None)
    
    @property
    def min_history_days_per_symbol(self) -> int:
        """Get minimum history days per symbol requirement"""
        return self.config.get('min_history_days_per_symbol', 730)
    
    def is_symbol_covered(self, symbol: str) -> bool:
        """
        Check if a symbol is covered by this model.
        
        Args:
            symbol: Trading symbol to check
            
        Returns:
            True if symbol is in trained_symbols, False otherwise
        """
        return symbol in self.trained_symbols
    
    def predict(self, features: Dict[str, float]) -> float:
        """
        Predict profitability probability for given features.
        
        Args:
            features: Dictionary of feature values
            
        Returns:
            Probability (0.0 to 1.0) that the signal will be profitable
        """
        if self.model is None or self.scaler is None:
            logger.error("Model or scaler not loaded")
            return 0.0
        
        try:
            # Convert features dict to array
            if self.feature_names:
                # Use feature names from config
                feature_array = np.array([
                    features.get(name, 0.0) for name in self.feature_names
                ]).reshape(1, -1)
            else:
                # Infer feature names from model
                if hasattr(self.model, 'feature_names_in_'):
                    feature_names = self.model.feature_names_in_
                    feature_array = np.array([
                        features.get(name, 0.0) for name in feature_names
                    ]).reshape(1, -1)
                else:
                    # Fallback: use all features in dict
                    feature_array = np.array([list(features.values())]).reshape(1, -1)
            
            # Scale features
            feature_array_scaled = self.scaler.transform(feature_array)
            
            # Predict probability
            if hasattr(self.model, 'predict_proba'):
                proba = self.model.predict_proba(feature_array_scaled)[0]
                # Return probability of positive class (index 1)
                # Handle both standard models and ensemble models
                if len(proba) > 1:
                    return float(proba[1])
                else:
                    return float(proba[0])
            elif hasattr(self.model, 'xgb_model') and hasattr(self.model, 'baseline_model'):
                # Ensemble model - use predict_proba from ensemble
                proba = self.model.predict_proba(feature_array_scaled)[0]
                return float(proba[1]) if len(proba) > 1 else float(proba[0])
            else:
                # Regression model - normalize to [0, 1]
                prediction = self.model.predict(feature_array_scaled)[0]
                return float(np.clip(prediction, 0.0, 1.0))
        
        except Exception as e:
            logger.error(f"Error making prediction: {e}")
            return 0.0

