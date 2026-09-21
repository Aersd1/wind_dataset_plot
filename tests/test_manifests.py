"""Synthetic manifest fixtures; no real power observations are used."""
import contextlib
import io
import json
import unittest
import pandas as pd
import numpy as np
from test_pipeline import Fixture
from wind_dataset_plot.manifests import read_plan, mapped_path
from wind_dataset_plot.io import discover, resolve_metadata, load_runs
from wind_dataset_plot.cli import main
from wind_dataset_plot.analysis import analyze


class ManifestTests(Fixture):
    def setUp(self):
        super().setUp()
        self.a = self.segment("farm_1", 1, [5.]*96, header=False)
        self.b = self.segment("farm_1", 2, [5.]*96, start="2020-01-03", header=False)
        self.c = self.segment("farm_2", 1, [10.]*96, header=False)
        # Deliberately nonexistent alternative and original files must never be read.
        self.long = pd.DataFrame([
            ["farm_1", "provider", "aligned_segments", str(self.a)],
            ["farm_1", "provider", "aligned_segments", str(self.b)],
            ["farm_2", "provider", "aligned_segments", str(self.c)],
            ["farm_1", "provider", "data_process", "/not/used/farm_1.csv"]],
            columns=["name", "source", "layer", "segment_csv_path"])
        self.cap = pd.DataFrame([
            ["farm_1", "provider", 10000, 10, "MW", "meta_parsed", "Onshore"],
            ["farm_2", "provider", 20000, 20, "MW", "fallback_uncut_power_max_MW", "Offshore"]],
            columns=["name", "source", "rated_power_kW_used", "rated_power_MW_used",
                     "power_unit_original_csv", "rated_capacity_source", "onshore_offshore"])
        self.orig = pd.DataFrame([["farm_1", "provider", "/not/used/original1.csv"],
                                  ["farm_2", "provider", "/not/used/original2.csv"]],
                                 columns=["name", "source", "original_csv_path"])
        self.cfg["inputs"].update(segments_manifest=str(self.root/"long.csv"),
                                  capacity_table=str(self.root/"capacity.csv"),
                                  original_manifest=str(self.root/"original.csv"))
        self.cfg["defaults"].update(value_unit="MW", value_column="power", timestamp_position="instantaneous")
        self.meta("farm_1", capacity=123)  # Table overrides JSON capacity and unit.
        p = self.meta("farm_2", "offshore", capacity=456)
        obj = json.loads(p.read_text()); obj["value_unit"] = "zscore"
        p.write_text(json.dumps(obj))
        self.write_tables()

    def write_tables(self):
        self.long.to_csv(self.root/"long.csv", index=False)
        self.cap.to_csv(self.root/"capacity.csv", index=False)
        self.orig.to_csv(self.root/"original.csv", index=False)

    def test_aligned_grouping_mw_and_capacity_authority(self):
        datasets = self.datasets()
        self.assertEqual([(d.id, len(d.files)) for d in datasets], [("farm_1", 2), ("farm_2", 1)])
        for ds in datasets:
            runs, _, _, _ = load_runs(ds)
            for run in runs: np.testing.assert_allclose(run, .5)
        self.cfg["plots"]["panels"] = ["a"]
        result = analyze(datasets, self.cfg)
        self.assertEqual(len(result["summary"]), 2)
        self.assertEqual(result["coverage"].max().max(), 2)
        self.assertEqual(result["summary"].capacity_is_proxy.sum(), 1)
        self.assertEqual(set(result["summary"].input_layer), {"aligned_segments"})

    def test_inspect_never_opens_series_or_json(self):
        self.long["segment_csv_path"] = [f"/missing/{n}.csv" for n in range(4)]
        self.write_tables()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["--config", str(self.config_file()), "--inspect-manifests"]), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["selected_segments"], 3)
        self.assertEqual(report["selected_farms"], 2)
        self.assertEqual(report["capacity_proxy_farms"], ["farm_2"])
        self.assertFalse((self.root/"results").exists())

    def test_wide_long_equivalence(self):
        wide = pd.DataFrame([
            ["farm_1", "provider", str(self.a)+"|"+str(self.b), "/not/used/farm_1.csv", 2, 1],
            ["farm_2", "provider", str(self.c), "", 1, 0]],
            columns=["name", "source", "aligned_segment_paths", "data_process_segment_paths",
                     "n_aligned_segments", "n_data_process_segments"])
        before, report = read_plan(self.cfg)
        wide.to_csv(self.root/"wide.csv", index=False)
        self.cfg["inputs"]["segments_manifest"] = str(self.root/"wide.csv")
        after, other = read_plan(self.cfg)
        self.assertEqual(before, after); self.assertEqual(report, other)
        wide.loc[0, "n_aligned_segments"] = 3
        wide.to_csv(self.root/"wide.csv", index=False)
        with self.assertRaisesRegex(ValueError, "disagrees"): read_plan(self.cfg)

    def test_layer_policies_never_mix(self):
        self.cfg["inputs"]["segment_layer"] = "prefer_data_process"
        farms, report = read_plan(self.cfg)
        self.assertEqual([f["layer"] for f in farms], ["data_process", "aligned_segments"])
        self.assertEqual(report["aligned_fallback_farms"], ["farm_2"])
        self.cfg["inputs"]["segment_layer"] = "data_process"
        farms, report = read_plan(self.cfg)
        self.assertEqual(len(farms), 1); self.assertEqual(report["excluded_farms"], ["farm_2"])

    def test_source_mismatch_rejected(self):
        self.cap.loc[0, "source"] = "wrong"; self.write_tables()
        with self.assertRaisesRegex(ValueError, "Missing farm capacity"): read_plan(self.cfg)

    def test_missing_capacity_rejected(self):
        self.cap = self.cap.iloc[1:]; self.write_tables()
        with self.assertRaisesRegex(ValueError, "Missing farm capacity"): read_plan(self.cfg)

    def test_duplicate_capacity_rejected(self):
        self.cap = pd.concat([self.cap, self.cap.iloc[:1]]); self.write_tables()
        with self.assertRaisesRegex(ValueError, "duplicate farm"): read_plan(self.cfg)

    def test_capacity_units_consistent(self):
        self.cap.loc[0, "rated_power_MW_used"] = 999; self.write_tables()
        with self.assertRaisesRegex(ValueError, "kW/MW"): read_plan(self.cfg)

    def test_invalid_capacity_rejected(self):
        self.cap.loc[0, "rated_power_kW_used"] = -1; self.write_tables()
        with self.assertRaisesRegex(ValueError, "positive"): read_plan(self.cfg)

    def test_energy_unit_and_end_timestamp_rejected(self):
        self.cfg["defaults"]["value_unit"] = "kWh"
        with self.assertRaisesRegex(ValueError, "requires value_unit=MW"): discover(self.cfg)
        self.cfg["defaults"].update(value_unit="MW", timestamp_position="end")
        with self.assertRaisesRegex(ValueError, "timestamp_position=end"): discover(self.cfg)

    def test_json_site_type_still_required_and_checked(self):
        self.cap.loc[0, "onshore_offshore"] = "Offshore"; self.write_tables()
        with self.assertRaisesRegex(ValueError, "JSON site type disagrees"): self.datasets()

    def test_missing_selected_file_fails(self):
        self.a.unlink()
        with self.assertRaisesRegex(FileNotFoundError, "missing selected segment"): discover(self.cfg)

    def test_path_prefix_mapping_and_boundary(self):
        mapping = {"/old": str(self.root), "/old/deep": str(self.root/"raw")}
        self.assertEqual(mapped_path("/old/deep/test.csv", "a.csv", mapping), self.root/"raw"/"test.csv")
        self.assertEqual(str(mapped_path("/older/test.csv", "a.csv", mapping)).replace("\\", "/"), "/older/test.csv")
        self.long.loc[0, "segment_csv_path"] = "/remote/a.csv"
        self.cfg["inputs"]["path_prefix_map"] = {"/remote": str(self.a.parent)}
        self.write_tables()
        farms, _ = read_plan(self.cfg)
        self.assertEqual(farms[0]["files"][0], self.a.parent/"a.csv")

    def test_duplicate_and_cross_farm_paths_rejected(self):
        self.long = pd.concat([self.long, self.long.iloc[:1]]); self.write_tables()
        with self.assertRaisesRegex(ValueError, "Duplicate path"): read_plan(self.cfg)
        self.long = self.long.iloc[:-1].copy()
        self.long.loc[2, "segment_csv_path"] = str(self.a); self.write_tables()
        with self.assertRaisesRegex(ValueError, "multiple farms"): read_plan(self.cfg)

    def test_manifest_end_to_end_exports_provenance(self):
        self.cfg["plots"].update(panels=["b", "c"], combined=False)
        self.assertEqual(main(["--config", str(self.config_file())]), 0)
        out = self.root/"results"
        manifest = json.loads((out/"run_manifest.json").read_text())
        self.assertEqual(manifest["original_dataset_count"], 2)
        self.assertEqual(manifest["segment_count"], 3)
        self.assertEqual(manifest["datasets"][1]["provenance"]["capacity_is_proxy"], True)
        self.assertIn("observed-maximum proxies", (out/"figure_description.md").read_text())


if __name__ == "__main__":
    unittest.main()
