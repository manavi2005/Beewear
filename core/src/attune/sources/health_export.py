"""Apple Health export parser (ADR-006): the batch fallback for Apple Watch vitals.

This is the vitals path that needs **no app signing** — the user exports their Health data
from the iPhone Health app (tap avatar → Export All Health Data → ``apple_health_export.zip``)
and points ``ATTUNE_HEALTH_EXPORT_PATH`` at the ``export.xml`` inside (or at the .zip).

The XML can be hundreds of MB, so we stream it with ``iterparse`` and clear elements as we
go rather than loading the whole tree.

Reminder (ADR-002): these signals come exclusively from the Apple Watch / HealthKit, never
from Bee.
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Iterable, Iterator
from datetime import datetime
from xml.etree import ElementTree as ET

from attune.models import VitalSample, VitalType

# HealthKit record type identifier → our canonical VitalType.
_TYPE_MAP: dict[str, VitalType] = {
    "HKQuantityTypeIdentifierHeartRate": VitalType.heart_rate,
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": VitalType.hrv_sdnn,
    "HKQuantityTypeIdentifierRespiratoryRate": VitalType.respiratory_rate,
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": VitalType.wrist_temperature,
    "HKCategoryTypeIdentifierSleepAnalysis": VitalType.sleep,
    # Movement as a coarse activity proxy; optional.
    "HKQuantityTypeIdentifierStepCount": VitalType.movement,
}


def _parse_hk_date(value: str | None) -> int | None:
    """Apple exports dates like '2026-10-09 14:05:33 -0700' → UTC epoch ms (ADR-008)."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.strptime(value, fmt).timestamp() * 1000)
        except ValueError:
            continue
    return None


def _sleep_value(raw_value: str) -> float:
    """Sleep is categorical in HealthKit; map 'asleep*' states to 1.0, everything else 0.0."""
    return 1.0 if raw_value and "Asleep" in raw_value else 0.0


class HealthExportSource:
    """Streams :class:`VitalSample` objects out of an Apple Health ``export.xml``."""

    name = "health_export"

    def __init__(self, path: str):
        self.path = path

    def fetch(self, start_ms: int, end_ms: int) -> Iterable[VitalSample]:
        return [s for s in self._iter_samples() if start_ms <= s.ts_ms <= end_ms]

    # ── streaming XML ───────────────────────────────────────────────────────────
    def _open(self):
        """Yield a file object for export.xml, whether given a .zip or a raw .xml path."""
        if self.path.endswith(".zip") or zipfile.is_zipfile(self.path):
            zf = zipfile.ZipFile(self.path)
            inner = next(
                (n for n in zf.namelist() if n.endswith("export.xml")), None
            )
            if inner is None:
                raise FileNotFoundError(f"No export.xml inside {self.path}")
            return zf.open(inner)
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"Health export not found: {self.path}")
        return open(self.path, "rb")

    def _iter_samples(self) -> Iterator[VitalSample]:
        fh = self._open()
        try:
            for _event, elem in ET.iterparse(fh, events=("end",)):
                if elem.tag != "Record":
                    continue
                hk_type = elem.get("type")
                vtype = _TYPE_MAP.get(hk_type) if hk_type else None
                if vtype is None:
                    elem.clear()
                    continue
                ts = _parse_hk_date(elem.get("startDate"))
                end = _parse_hk_date(elem.get("endDate"))
                raw_value = elem.get("value", "")
                unit = elem.get("unit", "")
                if ts is not None:
                    try:
                        value = (
                            _sleep_value(raw_value)
                            if vtype is VitalType.sleep
                            else float(raw_value)
                        )
                        yield VitalSample(
                            type=vtype,
                            ts_ms=ts,
                            end_ms=end,
                            value=value,
                            unit=unit or ("category" if vtype is VitalType.sleep else ""),
                            source="health_export",
                        )
                    except ValueError:
                        pass
                elem.clear()  # free memory as we stream (large exports)
        finally:
            fh.close()
