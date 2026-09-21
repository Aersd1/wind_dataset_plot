# Local verification

Verified on 2026-09-21, Windows, Python 3.14.3.

```text
python -m unittest discover -s tests -v
Ran 43 tests
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

The manifest update adds 15 synthetic tests covering long/wide equivalence, exact farm/source joins, processing-layer isolation, MW normalization against table capacities, JSON site-type checks, proxy-capacity provenance, missing/duplicate inputs, path remapping, and an end-to-end export.

Read-only inspection of the supplied index tables found 131 farms, 2,168 total path rows, and 1,770 selected aligned_segments paths. Long and wide manifests produced identical plans. Four supplied capacities are explicitly marked as observed-maximum proxies. These checks read the index tables only, not the power time series or remote JSON files.

No real research time series were analyzed, no real-data figures were produced, and no original CSV/JSON files are bundled here. In the supplied manifest profile, raw power is explicitly instantaneous MW and capacity comes from rated_power_kW_used. Server paths, timestamp format and timezone still need to match the actual CSVs. `--inspect-manifests` checks only index tables. `--validate-only` additionally checks identity/metadata/columns without numerical analysis; the full run validates timestamps, duplicates, cadence and gaps.

The GitHub workflow also defines synthetic tests on Linux/Python 3.10 and 3.12; those environments are distinct from this local verification.
