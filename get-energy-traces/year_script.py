"""Build a 365-day average energy-intensity profile from ENTSO-E data."""

from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from entsoe import EntsoeRawClient
from entsoe.exceptions import NoMatchingDataError
from entsoe.mappings import PSRTYPE_MAPPINGS, lookup_area


PROJECT_DIR = Path(__file__).resolve().parent

# Carbon is measured in gCO2eq/kWh and water in L/kWh.
CARBON_INTENSITIES = {
    "Biomass": 230.0,
    "Fossil Brown coal/Lignite": 630.0,
    "Fossil Coal-derived gas": 850.0,
    "Fossil Gas": 280.0,
    "Fossil Hard coal": 630.0,
    "Fossil Oil": 280.0,
    "Fossil Oil shale": 630.0,
    "Fossil Peat": 630.0,
    "Geothermal": 38.0,
    "Hydro Pumped Storage": 81.0,
    "Hydro Run-of-river and poundage": 81.0,
    "Hydro Water Reservoir": 81.0,
    "Marine": 17.0,
    "Nuclear": 5.1,
    "Other renewable": 21.0,
    "Solar": 21.0,
    "Waste": 230.0,
    "Wind Offshore": 13.0,
    "Wind Onshore": 12.0,
    "Energy storage": 21.0,
    "Other": 0.0,
    "Mixed": 0.0,
    "Generation": 0.0,
}

WATER_INTENSITIES = {
    "Biomass": 1.147,
    "Fossil Brown coal/Lignite": 1.802,
    "Fossil Coal-derived gas": 1.438,
    "Fossil Gas": 1.086,
    "Fossil Hard coal": 1.802,
    "Fossil Oil": 1.086,
    "Fossil Oil shale": 1.802,
    "Fossil Peat": 1.802,
    "Geothermal": 0.95,
    "Hydro Pumped Storage": 17.0,
    "Hydro Run-of-river and poundage": 17.0,
    "Hydro Water Reservoir": 17.0,
    "Marine": 0.0,
    "Nuclear": 1.957,
    "Other renewable": 0.004,
    "Solar": 0.004,
    "Waste": 1.147,
    "Wind Offshore": 0.0,
    "Wind Onshore": 0.0,
    "Energy storage": 0.004,
    "Other": 0.0,
    "Mixed": 0.0,
    "Generation": 0.0,
}

PRODUCTION_TYPES = list(CARBON_INTENSITIES)
SUPPORTED_POWER_UNITS = {"MAW", "MW"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_text(element: ET.Element, name: str) -> str | None:
    wanted = name.lower()
    for child in element.iter():
        if _local_name(child.tag).lower() == wanted and child.text:
            return child.text.strip()
    return None


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    wanted = name.lower()
    return [
        child
        for child in element.iter()
        if _local_name(child.tag).lower() == wanted
    ]


def _resolution_minutes(value: str) -> int:
    seconds = pd.Timedelta(value).total_seconds()
    if seconds <= 0 or seconds % 60:
        raise ValueError(f"Unsupported ENTSO-E resolution: {value}")
    return int(seconds // 60)


def parse_generation_xml(xml_text: str) -> pd.DataFrame:
    """Parse generation intervals while preserving XML resolution and unit."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError("ENTSO-E returned invalid XML") from exc

    records: list[dict] = []

    for series in _children(root, "TimeSeries"):
        # Consumption series use an output bidding-zone domain.
        if any(
            _local_name(item.tag).lower() == "outbiddingzone_domain.mrid"
            for item in series.iter()
        ):
            continue

        psr_code = _find_text(series, "psrType")
        if not psr_code:
            continue
        production_type = PSRTYPE_MAPPINGS.get(psr_code, psr_code)
        if production_type not in PRODUCTION_TYPES:
            raise ValueError(
                f"No intensity factor configured for production type "
                f"{production_type!r} ({psr_code})"
            )

        unit = (_find_text(series, "quantity_Measure_Unit.name") or "").upper()
        if unit not in SUPPORTED_POWER_UNITS:
            raise ValueError(
                f"Expected generation power in MW/MAW, received {unit or 'no unit'}"
            )

        curve_type = (_find_text(series, "curveType") or "A01").upper()
        for period in _children(series, "Period"):
            interval = next(
                (
                    item
                    for item in period.iter()
                    if _local_name(item.tag).lower() == "timeinterval"
                ),
                None,
            )
            if interval is None:
                continue

            start_text = _find_text(interval, "start")
            end_text = _find_text(interval, "end")
            resolution_text = _find_text(period, "resolution")
            if not start_text or not end_text or not resolution_text:
                continue

            period_start = pd.Timestamp(start_text).tz_convert("UTC")
            period_end = pd.Timestamp(end_text).tz_convert("UTC")
            resolution = pd.Timedelta(resolution_text)
            resolution_minutes = _resolution_minutes(resolution_text)

            values: dict[int, float] = {}
            for point in _children(period, "Point"):
                position = _find_text(point, "position")
                quantity = _find_text(point, "quantity")
                if position and quantity:
                    values[int(position)] = float(quantity.replace(",", ""))

            slot_count = int((period_end - period_start) / resolution)
            previous_value: float | None = None
            for position in range(1, slot_count + 1):
                if position in values:
                    previous_value = values[position]
                elif curve_type != "A03" or previous_value is None:
                    continue

                start_time = period_start + (position - 1) * resolution
                records.append(
                    {
                        "production_type": production_type,
                        "start_time": start_time,
                        "end_time": min(start_time + resolution, period_end),
                        "value_mw": previous_value,
                        "resolution_minutes": resolution_minutes,
                        "unit": unit,
                    }
                )

    if not records:
        raise ValueError("No actual-generation records found in ENTSO-E XML")

    result = pd.DataFrame.from_records(records)
    result = result.drop_duplicates(
        subset=["production_type", "start_time", "end_time"],
        keep="first",
    )
    return result.sort_values(["production_type", "start_time"]).reset_index(drop=True)


def resolution_counts(records: pd.DataFrame) -> Counter[int]:
    return Counter(records["resolution_minutes"].astype(int))


def print_resolution_report(per_year: dict[int, Counter[int]]) -> int:
    total: Counter[int] = Counter()
    print("\nResolutions reported by ENTSO-E:")
    for year, counts in sorted(per_year.items()):
        total.update(counts)
        amount = sum(counts.values())
        summary = ", ".join(
            f"{minutes} min: {count / amount:.2%} ({count:,})"
            for minutes, count in sorted(counts.items())
        )
        print(f"  {year}: {summary}")

    amount = sum(total.values())
    summary = ", ".join(
        f"{minutes} min: {count / amount:.2%} ({count:,})"
        for minutes, count in sorted(total.items())
    )
    print(f"  Total: {summary}")
    suggested = min(total)
    print(f"  Smallest observed resolution: {suggested} min")
    return suggested


def parse_resolution_input(value: str) -> int:
    cleaned = value.strip().lower().removesuffix("min").strip()
    try:
        minutes = int(cleaned)
    except ValueError as exc:
        raise ValueError("Resolution must be an integer number of minutes") from exc
    if minutes <= 0 or 1440 % minutes:
        raise ValueError("Resolution must be positive and divide a 24-hour day")
    return minutes


def choose_resolution(suggested: int) -> int:
    if not sys.stdin.isatty():
        print(f"Non-interactive input: using {suggested} min.")
        return suggested

    while True:
        answer = input(f"Target resolution in minutes [{suggested}]: ").strip()
        try:
            return parse_resolution_input(answer or str(suggested))
        except ValueError as exc:
            print(f"Invalid value: {exc}")


def normalize_generation_year(
    records: pd.DataFrame,
    year: int,
    timezone: str,
    target_minutes: int,
) -> pd.DataFrame:
    """Convert variable-resolution MW intervals into fixed-duration MW bins."""
    target_minutes = parse_resolution_input(str(target_minutes))
    start_local = pd.Timestamp(year=year, month=1, day=1, tz=timezone)
    end_local = pd.Timestamp(year=year + 1, month=1, day=1, tz=timezone)
    start_utc = start_local.tz_convert("UTC")
    end_utc = end_local.tz_convert("UTC")

    bin_ns = target_minutes * 60 * 1_000_000_000
    start_ns = start_utc.value
    end_ns = end_utc.value
    bin_count = (end_ns - start_ns) // bin_ns
    if start_ns + bin_count * bin_ns != end_ns:
        raise ValueError("Target resolution does not cover the year exactly")

    type_index = {name: index for index, name in enumerate(PRODUCTION_TYPES)}
    weighted_mw = np.zeros((len(PRODUCTION_TYPES), bin_count), dtype=float)
    covered_ns = np.zeros_like(weighted_mw)
    present_types = set(records["production_type"])

    for row in records.itertuples(index=False):
        interval_start = max(pd.Timestamp(row.start_time).value, start_ns)
        interval_end = min(pd.Timestamp(row.end_time).value, end_ns)
        if interval_start >= interval_end:
            continue

        production_index = type_index[row.production_type]
        aligned = (
            (interval_start - start_ns) % bin_ns == 0
            and (interval_end - start_ns) % bin_ns == 0
        )
        if aligned:
            first = (interval_start - start_ns) // bin_ns
            last = (interval_end - start_ns) // bin_ns
            weighted_mw[production_index, first:last] += row.value_mw * bin_ns
            covered_ns[production_index, first:last] += bin_ns
            continue

        first = max(0, (interval_start - start_ns) // bin_ns)
        last = min(bin_count - 1, (interval_end - 1 - start_ns) // bin_ns)
        for bin_index in range(first, last + 1):
            bin_start = start_ns + bin_index * bin_ns
            bin_end = bin_start + bin_ns
            overlap = min(interval_end, bin_end) - max(interval_start, bin_start)
            if overlap > 0:
                weighted_mw[production_index, bin_index] += row.value_mw * overlap
                covered_ns[production_index, bin_index] += overlap

    with np.errstate(invalid="ignore", divide="ignore"):
        values = weighted_mw / covered_ns
    values[covered_ns < bin_ns] = np.nan

    for production_type in PRODUCTION_TYPES:
        if production_type not in present_types:
            values[type_index[production_type], :] = 0.0

    starts_utc = pd.date_range(
        start=start_utc,
        periods=bin_count,
        freq=f"{target_minutes}min",
    )
    starts_local = starts_utc.tz_convert(timezone)
    not_leap_day = ~(
        (starts_local.month == 2)
        & (starts_local.day == 29)
    )
    values = values[:, not_leap_day]

    expected_bins = 365 * 1440 // target_minutes
    if values.shape[1] != expected_bins:
        raise ValueError(
            f"Expected {expected_bins} canonical-year bins, got {values.shape[1]}"
        )

    return pd.DataFrame(values.T, columns=PRODUCTION_TYPES)


def make_average_intensity_profile(years: list[pd.DataFrame]) -> pd.DataFrame:
    if not years:
        raise ValueError("No yearly generation data available")

    stack = np.stack([year[PRODUCTION_TYPES].to_numpy(float) for year in years])
    valid_counts = np.sum(~np.isnan(stack), axis=0)
    totals = np.nansum(stack, axis=0)
    average_generation = np.divide(
        totals,
        valid_counts,
        out=np.full_like(totals, np.nan),
        where=valid_counts > 0,
    )

    total_generation = np.nansum(average_generation, axis=1)
    shares = np.divide(
        average_generation,
        total_generation[:, None],
        out=np.full_like(average_generation, np.nan),
        where=total_generation[:, None] > 0,
    )
    carbon_factors = np.array(
        [CARBON_INTENSITIES[name] for name in PRODUCTION_TYPES]
    )
    water_factors = np.array(
        [WATER_INTENSITIES[name] for name in PRODUCTION_TYPES]
    )
    carbon_intensity = np.nansum(shares * carbon_factors, axis=1)
    water_intensity = np.nansum(shares * water_factors, axis=1)
    no_generation = total_generation <= 0
    carbon_intensity[no_generation] = np.nan
    water_intensity[no_generation] = np.nan

    return pd.DataFrame(
        {
            "carbon_intensity": carbon_intensity,
            "water_intensity": water_intensity,
        }
    )


def load_or_download_year(
    client: EntsoeRawClient,
    country: str,
    year: int,
    timezone: str,
    cache_dir: Path,
    refresh_cache: bool,
) -> tuple[str, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{country}_{year}.xml"
    if cache_path.exists() and not refresh_cache:
        print(f"{year}: using cached data from {cache_path}")
        return cache_path.read_text(encoding="utf-8"), cache_path

    start = pd.Timestamp(year=year, month=1, day=1, tz=timezone)
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz=timezone)
    print(f"{year}: requesting ENTSO-E data for {country}...")
    xml_text = client.query_generation(
        country_code=country,
        start=start,
        end=end,
    )
    temporary_path = cache_path.with_suffix(".xml.tmp")
    temporary_path.write_text(xml_text, encoding="utf-8")
    temporary_path.replace(cache_path)
    return xml_text, cache_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a 365-day average carbon and water intensity profile."
    )
    parser.add_argument("country", help="ENTSO-E area code, such as DE, FR, or PL")
    parser.add_argument("start_year", type=int, help="First year, inclusive")
    parser.add_argument("end_year", type=int, help="Last year, inclusive")
    parser.add_argument(
        "--resolution",
        type=parse_resolution_input,
        help="Output resolution in minutes; prompts for a value when omitted",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_DIR / "outputs/generated_year_csv",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PROJECT_DIR / ".entsoe_cache",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore cached files and download them again",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.start_year > args.end_year:
        raise SystemExit("start_year must be less than or equal to end_year")

    load_dotenv(PROJECT_DIR / ".env")

    api_token = os.getenv("API_TOKEN") or os.getenv("ENTSOE_API_KEY")
    if not api_token:
        raise SystemExit("Set API_TOKEN or ENTSOE_API_KEY in .env")

    country = args.country.upper()
    try:
        area = lookup_area(country)
    except ValueError as exc:
        raise SystemExit(f"Invalid ENTSO-E country/area code: {country}") from exc

    client = EntsoeRawClient(api_key=api_token)
    cached_years: dict[int, Path] = {}
    per_year_counts: dict[int, Counter[int]] = {}

    for year in range(args.start_year, args.end_year + 1):
        try:
            xml_text, cache_path = load_or_download_year(
                client=client,
                country=country,
                year=year,
                timezone=area.tz,
                cache_dir=args.cache_dir,
                refresh_cache=args.refresh_cache,
            )
            records = parse_generation_xml(xml_text)
        except NoMatchingDataError:
            print(f"{year}: no data found; skipping year.")
            continue

        cached_years[year] = cache_path
        per_year_counts[year] = resolution_counts(records)

    if not cached_years:
        raise SystemExit("No ENTSO-E generation data found for the requested period")

    suggested = print_resolution_report(per_year_counts)
    target_minutes = args.resolution or choose_resolution(suggested)
    print(f"\nNormalizing to {target_minutes} min...")

    normalized_years: list[pd.DataFrame] = []
    for year, cache_path in sorted(cached_years.items()):
        records = parse_generation_xml(cache_path.read_text(encoding="utf-8"))
        normalized = normalize_generation_year(
            records=records,
            year=year,
            timezone=area.tz,
            target_minutes=target_minutes,
        )
        normalized_years.append(normalized)
        covered = normalized.notna().any(axis=1).mean()
        print(f"  {year}: {covered:.2%} of intervals contain data")

    output = make_average_intensity_profile(normalized_years)
    output.insert(
        0,
        "timestamp",
        np.arange(len(output), dtype=np.int64) * target_minutes * 60,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / (
        f"{country}_{args.start_year}-{args.end_year}_"
        f"year_res={target_minutes}min.csv"
    )
    output.to_csv(output_path, index=False)

    missing_rows = output[["carbon_intensity", "water_intensity"]].isna().any(axis=1)
    print(f"\nCSV written to: {output_path}")
    print(f"Rows: {len(output):,}; intervals without intensity: {missing_rows.sum():,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
