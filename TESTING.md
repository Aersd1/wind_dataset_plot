# Local verification

Verified on 2026-09-21, Windows, Python 3.14.3.

```text
python -m unittest discover -s tests -v
Ran 28 tests
OK

python -m pip check
No broken requirements found.
```

Tested libraries:

```text
numpy==2.5.2
pandas==3.0.5
matplotlib==3.11.1
scipy==1.18.0
statsmodels==0.15.0
scikit-learn==1.9.1
```

The end-to-end test used only synthetic time series: two original datasets, one split into two retained CSV segments. It produced all six panels plus the combined figure in PNG, PDF and SVG. The combined PNG and the single daily-pattern matrix were visually reviewed for overlapping labels and clipping. A separate test covered plasma and pagination.

No real research time series were analyzed, no real-data figures were produced, and no original CSV/JSON files are bundled here. Server paths, true input units, rated capacities, timestamp convention and timezone must be configured before a real run. `--validate-only` checks identity/metadata/columns without numerical analysis; the full run additionally validates timestamps, duplicates, cadence and gaps.

The GitHub workflow also defines synthetic tests on Linux/Python 3.10 and 3.12; those environments are distinct from this local verification.
