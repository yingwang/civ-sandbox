"""Calendar helpers and adaptive spans for long artificial histories."""

from dataclasses import dataclass
from typing import Iterable, Optional

from models import EpochRecord


def year_to_ordinal(year: int) -> int:
    """Map historical years to a continuous axis without a year zero."""

    if year == 0:
        raise ValueError("historical calendar has no year zero")
    return year if year < 0 else year - 1


def ordinal_to_year(ordinal: int) -> int:
    return ordinal if ordinal < 0 else ordinal + 1


def advance_year(year: int, years: int = 1) -> int:
    if years < 0:
        raise ValueError("years must be nonnegative")
    return ordinal_to_year(year_to_ordinal(year) + years)


def inclusive_years(start_year: int, end_year: int) -> int:
    distance = year_to_ordinal(end_year) - year_to_ordinal(start_year) + 1
    if distance <= 0:
        raise ValueError("end year must not precede start year")
    return distance


def format_year(year: int) -> str:
    return f"公元前{-year}年" if year < 0 else f"公元{year}年"


def format_period(start_year: int, end_year: int) -> str:
    if start_year == end_year:
        return format_year(start_year)
    return f"{format_year(start_year)}至{format_year(end_year)}"


@dataclass
class AdaptiveTimeline:
    """Choose coarse spans, then narrow them after disruptive resolutions."""

    end_year: int = 2026
    disruption_scale: float = 0.5

    def next_span(
        self, current_year: int, previous_record: Optional[EpochRecord] = None
    ) -> int:
        remaining = inclusive_years(current_year, self.end_year)
        base = self._base_span(current_year)
        if previous_record and self._is_disruptive(previous_record):
            base = max(1, int(round(base * self.disruption_scale)))
        return min(base, remaining, self._years_to_boundary(current_year))

    def spans(
        self,
        start_year: int,
        records: Optional[Iterable[EpochRecord]] = None,
    ) -> Iterable[int]:
        current = start_year
        previous = None
        record_iter = iter(records or [])
        while year_to_ordinal(current) <= year_to_ordinal(self.end_year):
            span = self.next_span(current, previous)
            yield span
            current = advance_year(current, span)
            previous = next(record_iter, None)

    @staticmethod
    def _base_span(year: int) -> int:
        if year <= -221:
            return 1
        if year < 1:
            return 55
        if year <= 1600:
            return 200
        if year <= 1900:
            return 100
        if year <= 2000:
            return 20
        if year <= 2020:
            return 5
        return 1

    @staticmethod
    def _is_disruptive(record: EpochRecord) -> bool:
        major_statuses = {"extinct", "fission", "failed", "cancelled"}
        return any(
            resolution.status in major_statuses or resolution.side_effects
            for resolution in record.resolutions
        )

    def _years_to_boundary(self, year: int) -> int:
        boundaries = (-220, 1, 1601, 1901, 2001, 2021)
        current = year_to_ordinal(year)
        future = [
            year_to_ordinal(boundary)
            for boundary in boundaries
            if year_to_ordinal(boundary) > current
        ]
        if not future:
            return inclusive_years(year, self.end_year)
        return min(future) - current
