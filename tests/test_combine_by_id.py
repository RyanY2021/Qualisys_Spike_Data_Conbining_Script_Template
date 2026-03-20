from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qualisys_spike_combining.combine_by_id import (
    combine_pair,
    expand_tsv_headers,
    extract_id,
    normalize_output_header,
    output_name_for_pair,
    pair_files,
    should_exclude_tsv_column,
    tsv_column_sort_key,
)


def _write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    metadata = [f"meta_{i}" for i in range(1, 13)]
    body = ["\t".join(header)] + ["\t".join(row) for row in rows]
    path.write_text("\n".join(metadata + body) + "\n", encoding="utf-8")


def _write_txt(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(header)
        writer.writerows(rows)


def test_extract_id_supports_expected_patterns() -> None:
    assert extract_id("T70_10001") == "10001"
    assert extract_id("T70_10001_6D") == "10001"
    assert extract_id("Focused Wave_001") == "1"
    assert extract_id("Focued Wave0001_6D") == "1"
    assert extract_id("other_name") is None


def test_should_exclude_tsv_column_rules() -> None:
    assert should_exclude_tsv_column("Frame")
    assert should_exclude_tsv_column("Residual")
    assert should_exclude_tsv_column("Residual_2")
    assert should_exclude_tsv_column("MOD 1 Residual")
    assert should_exclude_tsv_column("Rot[0]")
    assert should_exclude_tsv_column("MOD 2 Rot[8]")
    assert should_exclude_tsv_column("Unnamed_15")
    assert not should_exclude_tsv_column("MOD 1 X")


def test_expand_tsv_headers_propagates_mod_prefix() -> None:
    raw = ["Frame", "Time", "MOD 1 X", "Y", "Z", "Residual", "Rot[0]", "", "MOD 2 X", "Y"]
    expanded = expand_tsv_headers(raw)
    assert expanded == [
        "Frame",
        "Time",
        "MOD 1 X",
        "MOD 1 Y",
        "MOD 1 Z",
        "MOD 1 Residual",
        "MOD 1 Rot[0]",
        "",
        "MOD 2 X",
        "MOD 2 Y",
    ]


def test_normalize_output_header_uses_underscores() -> None:
    assert normalize_output_header("MOD 1 X") == "MOD_1_X"
    assert normalize_output_header("1 Ref") == "1_Ref"
    assert normalize_output_header("semi-sub X", source="tsv") == "semi_X"
    assert normalize_output_header("715", source="txt") == "wp15"
    assert normalize_output_header("704", source="txt") == "wp4"


def test_tsv_column_sort_key_orders_by_mod_then_field() -> None:
    headers = [
        "MOD 7 Z",
        "MOD 1 Y",
        "MOD 1 X",
        "MOD 4 Roll",
        "MOD 2 X",
        "MOD 7 X",
    ]
    ordered = sorted(headers, key=tsv_column_sort_key)
    assert ordered == [
        "MOD 1 X",
        "MOD 1 Y",
        "MOD 2 X",
        "MOD 4 Roll",
        "MOD 7 X",
        "MOD 7 Z",
    ]


def test_output_name_for_pair_prefers_txt_stem() -> None:
    assert (
        output_name_for_pair(Path("Focused Wave_001.txt"), pair_id="1")
        == "Focused Wave_001_combined.txt"
    )


def test_combine_pair_filters_columns_and_uses_overlap(tmp_path: Path) -> None:
    tsv = tmp_path / "T70_10001_6D.tsv"
    txt = tmp_path / "T70_10001.txt"
    out = tmp_path / "10001_combined.txt"

    _write_tsv(
        tsv,
        header=["Frame", "Time", "MOD 1 X", "Y", "Residual", "Rot[0]", ""],
        rows=[
            ["1", "0.00", "10", "100", "0.1", "1", ""],
            ["2", "0.01", "11", "101", "0.1", "1", ""],
            ["3", "0.02", "12", "102", "0.1", "1", ""],
            ["4", "0.03", "13", "103", "0.1", "1", ""],
        ],
    )
    _write_txt(
        txt,
        header=["Time", "load_a", "load_b"],
        rows=[
            ["0.01", "1", "2"],
            ["0.02", "3", "4"],
            ["0.03", "5", "6"],
            ["0.04", "7", "8"],
        ],
    )

    row_count, start, end = combine_pair(tsv_path=tsv, txt_path=txt, out_path=out, decimals=2)

    assert row_count == 3
    assert start == 0.01
    assert end == 0.03

    with out.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        rows = list(reader)

    assert header == ["Time", "MOD_1_X", "MOD_1_Y", "load_a", "load_b"]
    assert rows[0] == ["0.01", "11", "101", "1", "2"]
    assert rows[-1] == ["0.03", "13", "103", "5", "6"]


def test_pair_files_groups_by_numeric_id(tmp_path: Path) -> None:
    (tmp_path / "T70_10001_6D.tsv").write_text("", encoding="utf-8")
    (tmp_path / "T70_10001.txt").write_text("", encoding="utf-8")
    (tmp_path / "T70_10002_6D.tsv").write_text("", encoding="utf-8")
    (tmp_path / "Focused Wave0001_6D.tsv").write_text("", encoding="utf-8")
    (tmp_path / "Focused Wave_001.txt").write_text("", encoding="utf-8")
    (tmp_path / "Focused Wave0003_6D.tsv").write_text("", encoding="utf-8")
    (tmp_path / "Focused Wave_003.txt").write_text("", encoding="utf-8")
    (tmp_path / "ignore.csv").write_text("", encoding="utf-8")

    tsv_map, txt_map = pair_files(tmp_path)
    assert sorted(tsv_map.keys()) == ["1", "10001", "10002", "3"]
    assert sorted(txt_map.keys()) == ["1", "10001", "3"]
