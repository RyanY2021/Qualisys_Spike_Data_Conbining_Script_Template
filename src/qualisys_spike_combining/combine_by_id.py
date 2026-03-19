#!/usr/bin/env python3
"""Combine paired TSV/TXT files by ID and align them on overlapping time."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pair .txt and .tsv files by numeric ID in filename, align on common "
            "time range, and combine columns into output .txt files."
        )
    )
    parser.add_argument(
        "--input-dir",
        default="input_data",
        type=Path,
        help="Directory containing source .txt/.tsv files (default: input_data).",
    )
    parser.add_argument(
        "--output-dir",
        default="combined_output",
        type=Path,
        help="Directory for combined output files (default: combined_output).",
    )
    parser.add_argument(
        "--time-decimals",
        default=5,
        type=int,
        help="Decimal places used to align time values (default: 5).",
    )
    return parser.parse_args(argv)


def unique_headers(raw_headers: Sequence[str]) -> List[str]:
    """Normalize empty/duplicate headers into stable unique names."""
    result: List[str] = []
    counts: Dict[str, int] = {}

    for index, header in enumerate(raw_headers, start=1):
        normalized = header.strip()
        if not normalized:
            normalized = f"Unnamed_{index}"

        if normalized in counts:
            counts[normalized] += 1
            normalized = f"{normalized}_{counts[normalized]}"
        else:
            counts[normalized] = 1

        result.append(normalized)

    return result


def expand_tsv_headers(raw_headers: Sequence[str]) -> List[str]:
    """
    Expand compact Qualisys headers so per-body fields are explicit.

    Example block:
      MOD 1 X, Y, Z, Roll, ...
    becomes:
      MOD 1 X, MOD 1 Y, MOD 1 Z, MOD 1 Roll, ...
    """
    expanded: List[str] = []
    current_prefix: str | None = None
    field_pattern = re.compile(r"^(X|Y|Z|Roll|Pitch|Yaw|Residual|Rot\[\d+\])$")
    prefixed_pattern = re.compile(
        r"^(.+)\s+(X|Y|Z|Roll|Pitch|Yaw|Residual|Rot\[\d+\])$"
    )

    for cell in raw_headers:
        header = cell.strip()
        if not header:
            expanded.append(header)
            current_prefix = None
            continue

        prefixed_match = prefixed_pattern.match(header)
        if prefixed_match:
            current_prefix = prefixed_match.group(1).strip()
            expanded.append(header)
            continue

        if current_prefix and field_pattern.match(header):
            expanded.append(f"{current_prefix} {header}")
            continue

        expanded.append(header)

    return expanded


def extract_id(stem: str) -> str | None:
    """
    Extract pair ID from filename stem.
    Examples:
      T70_10001       -> 10001
      T70_10001_6D    -> 10001
    """
    match = re.search(r"_(\d+)(?:_6D)?$", stem, flags=re.IGNORECASE)
    return match.group(1) if match else None


def read_tsv(tsv_path: Path) -> Tuple[List[str], List[List[str]], List[float], int]:
    """
    Read TSV where table header is on row 13 (1-based), data starts below it.
    Returns: headers, rows, time_values, time_col_idx
    """
    with tsv_path.open("r", encoding="utf-8-sig", newline="") as file:
        lines = file.readlines()

    if len(lines) < 13:
        raise ValueError(f"{tsv_path.name}: fewer than 13 rows; cannot read table.")

    header_row = next(csv.reader([lines[12]], delimiter="\t"))
    headers = unique_headers(expand_tsv_headers(header_row))

    try:
        time_idx = headers.index("Time")
    except ValueError as exc:
        raise ValueError(f"{tsv_path.name}: no 'Time' column found in row 13.") from exc

    data_rows: List[List[str]] = []
    time_values: List[float] = []

    for raw_row in csv.reader(lines[13:], delimiter="\t"):
        if not raw_row:
            continue
        if len(raw_row) < len(headers):
            raw_row += [""] * (len(headers) - len(raw_row))
        elif len(raw_row) > len(headers):
            raw_row = raw_row[: len(headers)]

        try:
            time_value = float(raw_row[time_idx].strip())
        except ValueError:
            continue

        data_rows.append(raw_row)
        time_values.append(time_value)

    if not data_rows:
        raise ValueError(f"{tsv_path.name}: no valid numeric time rows found.")

    return headers, data_rows, time_values, time_idx


def read_txt(txt_path: Path) -> Tuple[List[str], List[List[str]], List[float], int]:
    """Read tab-delimited TXT with header on first row."""
    with txt_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file, delimiter="\t")
        rows = [row for row in reader if row]

    if not rows:
        raise ValueError(f"{txt_path.name}: file is empty.")

    headers = unique_headers(rows[0])

    try:
        time_idx = headers.index("Time")
    except ValueError as exc:
        raise ValueError(f"{txt_path.name}: no 'Time' column found.") from exc

    data_rows: List[List[str]] = []
    time_values: List[float] = []

    for raw_row in rows[1:]:
        if len(raw_row) < len(headers):
            raw_row += [""] * (len(headers) - len(raw_row))
        elif len(raw_row) > len(headers):
            raw_row = raw_row[: len(headers)]

        try:
            time_value = float(raw_row[time_idx].strip())
        except ValueError:
            continue

        data_rows.append(raw_row)
        time_values.append(time_value)

    if not data_rows:
        raise ValueError(f"{txt_path.name}: no valid numeric time rows found.")

    return headers, data_rows, time_values, time_idx


def time_key(time_value: float, decimals: int) -> str:
    return f"{time_value:.{decimals}f}"


def should_exclude_tsv_column(header: str) -> bool:
    """Columns to drop from TSV before merging."""
    return (
        header == "Frame"
        or header.startswith("Frame_")
        or header.startswith("Unnamed_")
        or "Residual" in header
        or "Rot[" in header
    )


def normalize_output_header(header: str) -> str:
    """Normalize output header to underscore-separated style."""
    normalized = re.sub(r"\s+", "_", header.strip())
    normalized = re.sub(r"_+", "_", normalized)
    return normalized


def tsv_column_sort_key(header: str) -> tuple[int, int, int, str]:
    """
    Sort MOD columns as MOD 1..7 and X/Y/Z/Roll/Pitch/Yaw order.
    Non-MOD columns are kept after MOD columns.
    """
    mod_match = re.match(r"^MOD\s+(\d+)\s+(.+)$", header.strip())
    if not mod_match:
        return (1, 9999, 9999, header)

    mod_num = int(mod_match.group(1))
    field = mod_match.group(2).strip()
    field_order = {
        "X": 0,
        "Y": 1,
        "Z": 2,
        "Roll": 3,
        "Pitch": 4,
        "Yaw": 5,
    }
    return (0, mod_num, field_order.get(field, 999), field)


def build_overlap_map(
    rows: Sequence[Sequence[str]],
    times: Sequence[float],
    time_idx: int,
    start: float,
    end: float,
    decimals: int,
) -> Dict[str, List[str]]:
    mapped: Dict[str, List[str]] = {}

    for row, t in zip(rows, times):
        if t < start or t > end:
            continue
        key = time_key(t, decimals)
        if key in mapped:
            continue
        row_copy = list(row)
        row_copy[time_idx] = key
        mapped[key] = row_copy

    return mapped


def combine_pair(
    tsv_path: Path,
    txt_path: Path,
    out_path: Path,
    decimals: int,
) -> Tuple[int, float, float]:
    tsv_headers, tsv_rows, tsv_times, tsv_time_idx = read_tsv(tsv_path)
    txt_headers, txt_rows, txt_times, txt_time_idx = read_txt(txt_path)

    overlap_start = max(min(tsv_times), min(txt_times))
    overlap_end = min(max(tsv_times), max(txt_times))

    if overlap_end < overlap_start:
        raise ValueError("No time overlap between paired files.")

    tsv_map = build_overlap_map(
        rows=tsv_rows,
        times=tsv_times,
        time_idx=tsv_time_idx,
        start=overlap_start,
        end=overlap_end,
        decimals=decimals,
    )
    txt_map = build_overlap_map(
        rows=txt_rows,
        times=txt_times,
        time_idx=txt_time_idx,
        start=overlap_start,
        end=overlap_end,
        decimals=decimals,
    )

    common_times = sorted(set(tsv_map) & set(txt_map), key=float)
    if not common_times:
        raise ValueError("No aligned timestamps after overlap trimming.")

    tsv_keep_indices = [
        i
        for i in range(len(tsv_headers))
        if i != tsv_time_idx and not should_exclude_tsv_column(tsv_headers[i])
    ]
    tsv_keep_indices.sort(key=lambda i: tsv_column_sort_key(tsv_headers[i]))
    txt_keep_indices = [i for i in range(len(txt_headers)) if i != txt_time_idx]

    out_headers = (
        ["Time"]
        + [normalize_output_header(tsv_headers[i]) for i in tsv_keep_indices]
        + [normalize_output_header(txt_headers[i]) for i in txt_keep_indices]
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter="\t")
        writer.writerow(out_headers)

        for t in common_times:
            tsv_row = tsv_map[t]
            txt_row = txt_map[t]
            writer.writerow(
                [t]
                + [tsv_row[i] for i in tsv_keep_indices]
                + [txt_row[i] for i in txt_keep_indices]
            )

    return len(common_times), float(common_times[0]), float(common_times[-1])


def pair_files(input_dir: Path) -> Tuple[Dict[str, Path], Dict[str, Path]]:
    tsv_by_id: Dict[str, Path] = {}
    txt_by_id: Dict[str, Path] = {}

    for path in input_dir.iterdir():
        if not path.is_file():
            continue

        ext = path.suffix.lower()
        if ext not in {".tsv", ".txt"}:
            continue

        pair_id = extract_id(path.stem)
        if not pair_id:
            continue

        if ext == ".tsv":
            tsv_by_id[pair_id] = path
        else:
            txt_by_id[pair_id] = path

    return tsv_by_id, txt_by_id


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir

    if not input_dir.exists():
        print(f"[ERROR] Input directory not found: {input_dir}")
        return 1

    tsv_by_id, txt_by_id = pair_files(input_dir)
    common_ids = sorted(set(tsv_by_id) & set(txt_by_id))

    if not common_ids:
        print("[ERROR] No matching .tsv/.txt file pairs found by ID.")
        return 1

    missing_txt = sorted(set(tsv_by_id) - set(txt_by_id))
    missing_tsv = sorted(set(txt_by_id) - set(tsv_by_id))

    if missing_txt:
        print(f"[WARN] Missing .txt for IDs: {', '.join(missing_txt)}")
    if missing_tsv:
        print(f"[WARN] Missing .tsv for IDs: {', '.join(missing_tsv)}")

    print(f"[INFO] Found {len(common_ids)} pair(s) to combine.")

    success_count = 0
    for pair_id in common_ids:
        tsv_path = tsv_by_id[pair_id]
        txt_path = txt_by_id[pair_id]
        out_path = output_dir / f"{pair_id}_combined.txt"

        try:
            rows, start_time, end_time = combine_pair(
                tsv_path=tsv_path,
                txt_path=txt_path,
                out_path=out_path,
                decimals=args.time_decimals,
            )
            print(
                f"[OK] {pair_id}: rows={rows}, "
                f"time={start_time:.{args.time_decimals}f}.."
                f"{end_time:.{args.time_decimals}f}, out={out_path}"
            )
            success_count += 1
        except Exception as exc:
            print(f"[ERROR] {pair_id}: {exc}")

    print(f"[INFO] Completed: {success_count}/{len(common_ids)} pair(s) succeeded.")
    return 0 if success_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
