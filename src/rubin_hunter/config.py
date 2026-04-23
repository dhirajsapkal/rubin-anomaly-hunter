"""Config loading and validation. Thresholds are loaded from YAML and frozen
after the lock date per ADR-0006."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class CommonGate(BaseModel):
    min_detections_per_tracklet: int
    min_nights_spanned: int
    mpc_match_tolerance_arcsec: float
    max_streak_flag_fraction: float
    reliability_min: float
    cross_broker_quorum: int


class DarkCometThresholds(BaseModel):
    A1_min_au_per_day2: float
    A2_min_au_per_day2: float
    A3_min_au_per_day2: float
    max_relative_sigma: float
    max_extendedness: float
    max_eccentricity_upper: float


class ISOThresholds(BaseModel):
    min_best_fit_e: float
    max_sigma_e: float
    min_perihelion_au: float
    max_perihelion_au: float


class NullFieldBudget(BaseModel):
    dark_comet_max_per_night: int
    iso_max_per_week: int


class AnomalyScore(BaseModel):
    contamination: float
    random_seed: int


class Thresholds(BaseModel):
    schema_version: str
    locked: bool
    lock_target_date: str
    common: CommonGate
    dark_comet: DarkCometThresholds
    iso: ISOThresholds
    null_field_budget: NullFieldBudget
    anomaly_score: AnomalyScore


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "thresholds-commissioning.yaml"


def load_thresholds(path: Path | None = None) -> Thresholds:
    path = path or DEFAULT_CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        return Thresholds(**yaml.safe_load(f))
