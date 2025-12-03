"""Data quality checks and validation"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from loguru import logger


class DataQualityChecker:
    """Check data quality and integrity"""
    
    def __init__(self, expected_interval_minutes: int = 60):
        """
        Initialize data quality checker.
        
        Args:
            expected_interval_minutes: Expected interval between candles in minutes
        """
        self.expected_interval_minutes = expected_interval_minutes
        self.issues = []
        self.warnings = []
    
    def check_dataframe(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str
    ) -> Dict[str, any]:
        """
        Perform comprehensive data quality checks.
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading symbol
            timeframe: Timeframe string
            
        Returns:
            Dictionary with check results
        """
        self.issues = []
        self.warnings = []
        
        if df.empty:
            self.issues.append("DataFrame is empty")
            return self._format_results()
        
        # Check required columns
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            self.issues.append(f"Missing required columns: {missing_cols}")
            return self._format_results()
        
        # Check timestamp format
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            try:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            except:
                self.issues.append("Cannot convert timestamp to datetime")
                return self._format_results()
        
        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Check for duplicates
        duplicates = df.duplicated(subset=['timestamp']).sum()
        if duplicates > 0:
            self.issues.append(f"Found {duplicates} duplicate timestamps")
        
        # Check for gaps
        gap_results = self._check_gaps(df)
        if gap_results['total_gaps'] > 0:
            self.warnings.append(
                f"Found {gap_results['total_gaps']} gaps "
                f"(total missing time: {gap_results['total_missing_hours']:.1f} hours)"
            )
        
        # Check price validity
        price_issues = self._check_prices(df)
        self.issues.extend(price_issues)
        
        # Check volume validity
        volume_issues = self._check_volumes(df)
        self.issues.extend(volume_issues)
        
        # Check OHLC relationships
        ohlc_issues = self._check_ohlc_relationships(df)
        self.issues.extend(ohlc_issues)
        
        # Check for outliers
        outlier_warnings = self._check_outliers(df)
        self.warnings.extend(outlier_warnings)
        
        # Check data range
        if len(df) > 0:
            date_range = {
                'start': df['timestamp'].min(),
                'end': df['timestamp'].max(),
                'duration_days': (df['timestamp'].max() - df['timestamp'].min()).days,
                'candle_count': len(df)
            }
        else:
            date_range = {}
        
        return self._format_results(date_range)
    
    def _check_gaps(self, df: pd.DataFrame) -> Dict[str, any]:
        """Check for gaps in time series"""
        if len(df) < 2:
            return {'total_gaps': 0, 'total_missing_hours': 0, 'gaps': []}
        
        gaps = []
        total_missing_hours = 0
        
        for i in range(len(df) - 1):
            current_time = df.iloc[i]['timestamp']
            next_time = df.iloc[i + 1]['timestamp']
            expected_next = current_time + timedelta(minutes=self.expected_interval_minutes)
            
            if next_time > expected_next + timedelta(minutes=self.expected_interval_minutes * 0.5):
                gap_hours = (next_time - expected_next).total_seconds() / 3600
                gaps.append({
                    'start': current_time,
                    'end': next_time,
                    'missing_hours': gap_hours
                })
                total_missing_hours += gap_hours
        
        return {
            'total_gaps': len(gaps),
            'total_missing_hours': total_missing_hours,
            'gaps': gaps[:10]  # Limit to first 10 for reporting
        }
    
    def _check_prices(self, df: pd.DataFrame) -> List[str]:
        """Check price validity"""
        issues = []
        
        # Check for negative or zero prices
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            if (df[col] <= 0).any():
                count = (df[col] <= 0).sum()
                issues.append(f"{col}: {count} non-positive values")
        
        # Check for NaN
        for col in price_cols:
            if df[col].isna().any():
                count = df[col].isna().sum()
                issues.append(f"{col}: {count} NaN values")
        
        return issues
    
    def _check_volumes(self, df: pd.DataFrame) -> List[str]:
        """Check volume validity"""
        issues = []
        
        # Check for negative volumes
        if 'volume' in df.columns:
            if (df['volume'] < 0).any():
                count = (df['volume'] < 0).sum()
                issues.append(f"volume: {count} negative values")
            
            # Check for NaN
            if df['volume'].isna().any():
                count = df['volume'].isna().sum()
                issues.append(f"volume: {count} NaN values")
        
        return issues
    
    def _check_ohlc_relationships(self, df: pd.DataFrame) -> List[str]:
        """Check OHLC price relationships"""
        issues = []
        
        # High should be >= Open, Low, Close
        if ((df['high'] < df['open']) | (df['high'] < df['low']) | (df['high'] < df['close'])).any():
            count = ((df['high'] < df['open']) | (df['high'] < df['low']) | (df['high'] < df['close'])).sum()
            issues.append(f"high < (open|low|close): {count} violations")
        
        # Low should be <= Open, High, Close
        if ((df['low'] > df['open']) | (df['low'] > df['high']) | (df['low'] > df['close'])).any():
            count = ((df['low'] > df['open']) | (df['low'] > df['high']) | (df['low'] > df['close'])).sum()
            issues.append(f"low > (open|high|close): {count} violations")
        
        return issues
    
    def _check_outliers(self, df: pd.DataFrame) -> List[str]:
        """Check for statistical outliers"""
        warnings = []
        
        if len(df) < 10:
            return warnings
        
        # Check for extreme price changes
        df = df.copy()
        df['price_change_pct'] = df['close'].pct_change().abs()
        
        # Use IQR method for outlier detection
        Q1 = df['price_change_pct'].quantile(0.25)
        Q3 = df['price_change_pct'].quantile(0.75)
        IQR = Q3 - Q1
        outlier_threshold = Q3 + 3 * IQR
        
        outliers = df[df['price_change_pct'] > outlier_threshold]
        if len(outliers) > 0:
            warnings.append(f"Found {len(outliers)} extreme price changes (> {outlier_threshold:.2%})")
        
        # Check for zero volume periods
        if 'volume' in df.columns:
            zero_volume = (df['volume'] == 0).sum()
            if zero_volume > 0:
                warnings.append(f"Found {zero_volume} candles with zero volume")
        
        return warnings
    
    def _format_results(self, date_range: Optional[Dict] = None) -> Dict[str, any]:
        """Format check results"""
        return {
            'passed': len(self.issues) == 0,
            'issues': self.issues,
            'warnings': self.warnings,
            'issue_count': len(self.issues),
            'warning_count': len(self.warnings),
            'date_range': date_range or {}
        }
    
    def generate_report(
        self,
        results: Dict[str, any],
        symbol: str,
        timeframe: str,
        output_path: Optional[Path] = None
    ) -> str:
        """
        Generate human-readable quality report.
        
        Args:
            results: Check results dictionary
            symbol: Trading symbol
            timeframe: Timeframe
            output_path: Optional path to save report
            
        Returns:
            Report text
        """
        lines = [
            f"# Data Quality Report: {symbol} ({timeframe})",
            "",
            f"**Generated:** {datetime.utcnow().isoformat()}",
            "",
            "## Summary",
            "",
            f"- **Status:** {'✅ PASSED' if results['passed'] else '❌ FAILED'}",
            f"- **Issues:** {results['issue_count']}",
            f"- **Warnings:** {results['warning_count']}",
            ""
        ]
        
        if results['date_range']:
            dr = results['date_range']
            lines.extend([
                "## Data Range",
                "",
                f"- **Start:** {dr.get('start', 'N/A')}",
                f"- **End:** {dr.get('end', 'N/A')}",
                f"- **Duration:** {dr.get('duration_days', 0):.1f} days",
                f"- **Candle Count:** {dr.get('candle_count', 0)}",
                ""
            ])
        
        if results['issues']:
            lines.extend([
                "## Issues (Must Fix)",
                ""
            ])
            for issue in results['issues']:
                lines.append(f"- ❌ {issue}")
            lines.append("")
        
        if results['warnings']:
            lines.extend([
                "## Warnings (Review)",
                ""
            ])
            for warning in results['warnings']:
                lines.append(f"- ⚠️ {warning}")
            lines.append("")
        
        if results['passed'] and results['warning_count'] == 0:
            lines.append("✅ **All checks passed. Data quality is good.**")
        
        report_text = '\n'.join(lines)
        
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(report_text)
            logger.info(f"Quality report saved to {output_path}")
        
        return report_text

