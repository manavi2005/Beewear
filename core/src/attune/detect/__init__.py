"""Pluggable moment detectors (Strategy pattern, ADR-005)."""

from attune.detect.base import Detector
from attune.detect.rules import (
    DEFAULT_DETECTORS,
    HesitationDetector,
    RepeatedTopicDetector,
    SelfCorrectionDetector,
    UncertaintyDetector,
    VitalsDeltaDetector,
)

__all__ = [
    "Detector",
    "DEFAULT_DETECTORS",
    "HesitationDetector",
    "RepeatedTopicDetector",
    "SelfCorrectionDetector",
    "UncertaintyDetector",
    "VitalsDeltaDetector",
]
