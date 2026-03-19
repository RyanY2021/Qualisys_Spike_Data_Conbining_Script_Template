# Qualysis_Spike_Conbining

Combine paired Qualisys `.tsv` and load-cell `.txt` files by numeric ID, align by overlapping time, and export merged tab-delimited `.txt` files.

## 1. Purpose

This project automates:

1. Pairing files by ID in filenames (example: `T70_10001_6D.tsv` with `T70_10001.txt`).
2. Reading Qualisys TSV tables from row 13 header (data starts row 14).
3. Aligning start/end times using only shared overlap.
4. Removing redundant rows outside overlap.
5. Merging columns while excluding these TSV fields:
   - `Frame`
   - `Residual*`
   - `Rot[*]`
   - `Unnamed_*`

## 2. Environment Setup

Run from project root:

```bat
python -m pip install -e .
```

## 3. Data Layout

Input:

- `input_data/*.tsv`
- `input_data/*.txt`

Output:

- `combined_output/*_combined.txt`

## 4. Run

Default run:

```bat
python combine_by_id.py
```

or installed CLI:

```bat
qualisys-combine-by-id
```

With custom paths:

```bat
python combine_by_id.py --input-dir input_data --output-dir combined_output --time-decimals 5
```

## 5. Testing

Run:

```bat
python -m pytest
```

## 6. Repo Files

- `src/qualisys_spike_combining/` package source
- `tests/` unit tests
- `pyproject.toml` packaging and tool config
- `.pre-commit-config.yaml` formatting/lint hooks
- `.gitignore` local data/cache exclusions
