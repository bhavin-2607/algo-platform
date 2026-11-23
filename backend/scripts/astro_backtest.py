#!/usr/bin/env python3
"""
Financial Astrology & Cyclical Market Timing Backtester
======================================================
Standalone CLI research & validation tool that:
1. Loads historical OHLCV candles (from PostgreSQL, CSV, or synthetic generator).
2. Computes circular celestial features (sin/cos encoding, lunar phase, Nakshatras, aspect stress).
3. Executes an Event-Study Statistical Audit (scipy.stats.ttest_ind) testing volatility and return differentials on high-stress aspect days.
4. Performs a Strict Rolling Walk-Forward Out-of-Sample Machine Learning Validation (RandomForestClassifier, zero look-ahead bias).

Usage:
    python -m backend.scripts.astro_backtest --synthetic --days 500
    python backend/scripts/astro_backtest.py --csv-path data/nifty50_daily.csv
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple
import zoneinfo

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.astro_service import (
    IST,
    NAKSHATRAS,
    PLANET_CONFIGS,
    SPAN_NAKSHATRA,
    compute_active_aspects,
    compute_kp_sub_lord,
    get_planetary_telemetry,
)


def generate_synthetic_ohlcv(days: int = 500, symbol: str = "NIFTY50") -> pd.DataFrame:
    """Generate deterministic, realistic synthetic equity daily OHLCV series."""
    np.random.seed(42)
    end_date = datetime.now(IST).date()
    start_date = end_date - timedelta(days=int(days * 1.45))

    dates: List[date] = []
    curr = start_date
    while len(dates) < days:
        # Skip weekends (NSE trading days only)
        if curr.weekday() < 5:
            dates.append(curr)
        curr += timedelta(days=1)

    price = 22000.0
    records = []
    for d in dates:
        drift = 0.0003
        vol = 0.012
        ret = np.random.normal(drift, vol)
        open_price = price * (1.0 + np.random.normal(0, 0.003))
        high_price = max(open_price, open_price * (1.0 + abs(np.random.normal(0, 0.009))))
        low_price = min(open_price, open_price * (1.0 - abs(np.random.normal(0, 0.009))))
        close_price = low_price + (high_price - low_price) * np.random.uniform(0.15, 0.85)
        volume = int(np.random.lognormal(14.5, 0.5))

        records.append({
            "date": d,
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": volume,
            "symbol": symbol,
        })
        price = close_price

    df = pd.DataFrame(records)
    df["range_pct"] = (df["high"] - df["low"]) / df["low"] * 100.0
    df["return_pct"] = df["close"].pct_change() * 100.0
    return df


def load_ohlcv(csv_path: Optional[str] = None, days: int = 500, symbol: str = "NIFTY50") -> pd.DataFrame:
    """Load OHLCV data from CSV or synthetic generator."""
    if csv_path and os.path.exists(csv_path):
        print(f"[DATA] Loading historical OHLCV from CSV: {csv_path}")
        df = pd.read_csv(csv_path)
        col_map = {c.lower(): c for c in df.columns}
        date_col = next((col_map[c] for c in ["date", "datetime", "timestamp", "time"] if c in col_map), None)
        if not date_col:
            raise ValueError(f"Could not identify date column in {csv_path}")

        df["date"] = pd.to_datetime(df[date_col]).dt.date
        df = df.rename(columns={
            col_map.get("open", "open"): "open",
            col_map.get("high", "high"): "high",
            col_map.get("low", "low"): "low",
            col_map.get("close", "close"): "close",
            col_map.get("volume", "volume"): "volume",
        })
        df = df.sort_values("date").reset_index(drop=True)
        df["range_pct"] = (df["high"] - df["low"]) / df["low"] * 100.0
        df["return_pct"] = df["close"].pct_change() * 100.0
        return df

    print(f"[DATA] Generating {days} trading days of synthetic {symbol} market candles...")
    return generate_synthetic_ohlcv(days=days, symbol=symbol)


def compute_astro_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extracts circular (sin/cos) astronomical features for each trading day.
    Uses midday (12:00 IST) reference time to avoid boundary jitter.
    """
    print("[ASTRO] Computing Lahiri Sidereal ephemeris and planetary aspect features...")
    features_list = []

    for _, row in df.iterrows():
        d: date = row["date"]
        dt = datetime.combine(d, time(12, 0), tzinfo=IST)

        planets = get_planetary_telemetry(dt)
        aspects = compute_active_aspects(planets)

        hard_score = round(sum(a.weight for a in aspects if a.is_hard), 3)
        soft_score = round(sum(a.weight for a in aspects if not a.is_hard), 3)
        net_score = round(soft_score - hard_score, 3)

        stationary = [p for p in planets if p.is_stationary]
        volatility_alert = 1.0 if (hard_score >= 1.8 or len(stationary) > 0) else 0.0

        p_map = {p.name: p for p in planets}
        sun = p_map.get("Sun")
        moon = p_map.get("Moon")

        row_feat = {
            "hard_aspect_score": hard_score,
            "soft_aspect_score": soft_score,
            "net_sentiment_score": net_score,
            "volatility_alert": volatility_alert,
            "stationary_count": float(len(stationary)),
        }

        # Encode planetary longitudes with circular sin and cos
        for p in planets:
            rad = math.radians(p.longitude)
            row_feat[f"{p.name}_sin"] = math.sin(rad)
            row_feat[f"{p.name}_cos"] = math.cos(rad)
            row_feat[f"{p.name}_speed"] = p.speed
            row_feat[f"{p.name}_retrograde"] = 1.0 if p.is_retrograde else 0.0

        # Lunar phase angle: (Moon - Sun) % 360
        if sun and moon:
            phase_rad = math.radians((moon.longitude - sun.longitude) % 360.0)
            row_feat["lunar_phase_sin"] = math.sin(phase_rad)
            row_feat["lunar_phase_cos"] = math.cos(phase_rad)

            # Moon Nakshatra circular encoding (0 to 26 mapped to 0 to 2*pi)
            nak_idx = int(moon.longitude // SPAN_NAKSHATRA) % 27
            nak_rad = 2.0 * math.pi * nak_idx / 27.0
            row_feat["moon_nakshatra_sin"] = math.sin(nak_rad)
            row_feat["moon_nakshatra_cos"] = math.cos(nak_rad)

        features_list.append(row_feat)

    feat_df = pd.DataFrame(features_list)
    combined = pd.concat([df.reset_index(drop=True), feat_df], axis=1)

    # Next-bar forward return and binary directional target
    combined["fwd_return_1d"] = combined["close"].shift(-1) / combined["close"] - 1.0
    combined["target_up"] = (combined["fwd_return_1d"] > 0).astype(int)

    # Drop the final row since fwd_return_1d is NaN
    combined = combined.dropna(subset=["fwd_return_1d"]).reset_index(drop=True)
    return combined


def run_event_study(df: pd.DataFrame) -> dict:
    """
    Event-Study Statistical Audit comparing intraday range % and forward returns
    on top-quintile hard aspect stress days vs normal days using scipy.stats.ttest_ind.
    """
    print("\n" + "=" * 70)
    print("EVENT-STUDY STATISTICAL AUDIT (HIGH ASTRO STRESS VS NORMAL DAYS)")
    print("=" * 70)

    # Top quintile (80th percentile) on hard_aspect_score
    q80 = float(np.percentile(df["hard_aspect_score"], 80))
    stress_mask = df["hard_aspect_score"] >= q80
    normal_mask = ~stress_mask

    stress_ranges = df.loc[stress_mask, "range_pct"].dropna()
    normal_ranges = df.loc[normal_mask, "range_pct"].dropna()

    stress_returns = df.loc[stress_mask, "return_pct"].dropna()
    normal_returns = df.loc[normal_mask, "return_pct"].dropna()

    # Welch's two-sample t-test (unequal variances)
    t_stat_range, p_val_range = stats.ttest_ind(stress_ranges, normal_ranges, equal_var=False)
    t_stat_ret, p_val_ret = stats.ttest_ind(stress_returns, normal_returns, equal_var=False)

    print(f"Total Trading Days Analyzed:   {len(df)}")
    print(f"Top-Quintile Stress Cutoff:   hard_aspect_score >= {q80:.2f}")
    print(f"  - High-Stress Days:         {len(stress_ranges)} bars ({len(stress_ranges)/len(df)*100:.1f}%)")
    print(f"  - Normal Days:              {len(normal_ranges)} bars ({len(normal_ranges)/len(df)*100:.1f}%)")
    print("-" * 70)
    print("Intraday Range % [Volatility]:")
    print(f"  - High-Stress Days Mean:    {stress_ranges.mean():.3f}% ± {stress_ranges.std():.3f}%")
    print(f"  - Normal Days Mean:         {normal_ranges.mean():.3f}% ± {normal_ranges.std():.3f}%")
    print(f"  - Delta (Stress - Normal):  {stress_ranges.mean() - normal_ranges.mean():+.3f}%")
    print(f"  - Welch t-statistic:        {t_stat_range:.4f}")
    print(f"  - p-value:                  {p_val_range:.4e} {'[STATISTICALLY SIGNIFICANT (p < 0.05)]' if p_val_range < 0.05 else '[NOT SIGNIFICANT]'}")
    print("-" * 70)
    print("Daily Return % [Directional Bias]:")
    print(f"  - High-Stress Days Mean:    {stress_returns.mean():.3f}%")
    print(f"  - Normal Days Mean:         {normal_returns.mean():.3f}%")
    print(f"  - Welch t-statistic:        {t_stat_ret:.4f}")
    print(f"  - p-value:                  {p_val_ret:.4e}")
    print("=" * 70 + "\n")

    return {
        "n_total": len(df),
        "n_stress": len(stress_ranges),
        "n_normal": len(normal_ranges),
        "stress_range_mean": float(stress_ranges.mean()),
        "normal_range_mean": float(normal_ranges.mean()),
        "range_delta": float(stress_ranges.mean() - normal_ranges.mean()),
        "range_t_stat": float(t_stat_range),
        "range_p_val": float(p_val_range),
        "range_significant": bool(p_val_range < 0.05),
    }


def run_walk_forward_validation(df: pd.DataFrame, train_size: int = 200, test_size: int = 50) -> dict:
    """
    Strict Rolling Walk-Forward Out-of-Sample Validation.
    No shuffling, no look-ahead leakage. Trains on past bars, tests strictly on out-of-sample forward bars.
    """
    print("=" * 70)
    print(f"ROLLING WALK-FORWARD VALIDATION (TRAIN={train_size} BARS, TEST={test_size} BARS)")
    print("=" * 70)

    # Exclude non-feature columns
    excluded_cols = {"date", "open", "high", "low", "close", "volume", "symbol", "range_pct", "return_pct", "fwd_return_1d", "target_up"}
    feature_cols = [c for c in df.columns if c not in excluded_cols]

    n_samples = len(df)
    if n_samples < train_size + test_size:
        print(f"[WARN] Not enough samples ({n_samples}) for walk-forward window {train_size}+{test_size}. Reducing train size.")
        train_size = int(n_samples * 0.6)
        test_size = int(n_samples * 0.2)

    all_y_true: List[int] = []
    all_y_pred: List[int] = []
    all_y_prob: List[float] = []
    fold_accuracies: List[float] = []

    fold = 1
    start_idx = 0

    while start_idx + train_size + test_size <= n_samples:
        train_end = start_idx + train_size
        test_end = train_end + test_size

        X_train = df.loc[start_idx:train_end - 1, feature_cols]
        y_train = df.loc[start_idx:train_end - 1, "target_up"]

        X_test = df.loc[train_end:test_end - 1, feature_cols]
        y_test = df.loc[train_end:test_end - 1, "target_up"]

        # Train Random Forest with restricted depth to prevent overfitting
        clf = RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=10, random_state=42 + fold)
        clf.fit(X_train, y_train)

        probs = clf.predict_proba(X_test)[:, 1]
        preds = (probs >= 0.5).astype(int)

        acc = accuracy_score(y_test, preds)
        fold_accuracies.append(acc)

        all_y_true.extend(y_test.tolist())
        all_y_pred.extend(preds.tolist())
        all_y_prob.extend(probs.tolist())

        test_start_date = df.loc[train_end, "date"]
        test_end_date = df.loc[test_end - 1, "date"]
        print(f"  Fold {fold:02d} [{test_start_date} to {test_end_date}]: Out-of-Sample Accuracy = {acc*100:.2f}% (bars={len(y_test)})")

        fold += 1
        start_idx += test_size  # Non-overlapping out-of-sample forward test windows

    total_acc = accuracy_score(all_y_true, all_y_pred)
    try:
        total_auc = roc_auc_score(all_y_true, all_y_prob)
    except Exception:
        total_auc = 0.5

    print("-" * 70)
    print(f"Aggregate Out-of-Sample Accuracy:   {total_acc*100:.2f}% ({sum(fold_accuracies)/len(fold_accuracies)*100:.2f}% fold avg)")
    print(f"Aggregate Out-of-Sample ROC-AUC:    {total_auc:.4f}")
    print(f"Total Out-of-Sample Test Bars:      {len(all_y_true)}")
    print("-" * 70)

    # Feature Importance analysis on the full dataset
    clf_full = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
    clf_full.fit(df[feature_cols], df["target_up"])
    importances = pd.Series(clf_full.feature_importances_, index=feature_cols).sort_values(ascending=False)

    print("Top 10 Most Predictive Astro Features:")
    for rank, (feat, imp) in enumerate(importances.head(10).items(), 1):
        print(f"  {rank:02d}. {feat:<28} (Importance: {imp*100:.2f}%)")
    print("=" * 70 + "\n")

    return {
        "oos_accuracy": float(total_acc),
        "oos_roc_auc": float(total_auc),
        "folds_evaluated": fold - 1,
        "top_features": importances.head(10).to_dict(),
    }


def main():
    parser = argparse.ArgumentParser(description="Financial Astrology & Cyclical Timing Backtest Engine")
    parser.add_argument("--csv-path", type=str, default=None, help="Path to historical OHLCV CSV file")
    parser.add_argument("--days", type=int, default=500, help="Number of trading days (default: 500)")
    parser.add_argument("--symbol", type=str, default="NIFTY50", help="Ticker symbol (default: NIFTY50)")
    parser.add_argument("--synthetic", action="store_true", help="Force synthetic data generation")

    args = parser.parse_args()

    csv_target = None if args.synthetic else args.csv_path
    df_raw = load_ohlcv(csv_path=csv_target, days=args.days, symbol=args.symbol)
    df_astro = compute_astro_features(df_raw)

    event_results = run_event_study(df_astro)
    wf_results = run_walk_forward_validation(df_astro)

    print("[SUCCESS] Financial Astrology Research & Backtest Completed.")


if __name__ == "__main__":
    main()
