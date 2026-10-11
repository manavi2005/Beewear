"""Pluggable moment detectors (Strategy pattern, ADR-005)."""

from attune.detect.base import Detector
from attune.detect.rules import (
    DEFAULT_DETECTORS,
    GENERIC_DETECTORS,
    NEUROLEARN_DETECTORS,
    CheckInDetector,
    ConceptLinkDetector,
    HesitationDetector,
    RepeatedTopicDetector,
    SelfCorrectionDetector,
    StudyObjectiveDetector,
    UncertaintyDetector,
    VitalsDeltaDetector,
    build_detectors,
)

__all__ = [
    "Detector",
    "DEFAULT_DETECTORS",
    "GENERIC_DETECTORS",
    "NEUROLEARN_DETECTORS",
    "CheckInDetector",
    "ConceptLinkDetector",
    "HesitationDetector",
    "RepeatedTopicDetector",
    "SelfCorrectionDetector",
    "StudyObjectiveDetector",
    "UncertaintyDetector",
    "VitalsDeltaDetector",
    "build_detectors",
]
