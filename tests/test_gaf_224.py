import unittest
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from gaf_224.__main__ import candidate_windows, gasf, matrix_features, run, spread_indices


class Gaf224Tests(unittest.TestCase):
    def test_gasf_identity_and_size(self):
        cf = np.linspace(0, 1, 224)
        image = gasf(cf)
        x = 2 * cf - 1
        np.testing.assert_allclose(np.diag(image), 2 * x * x - 1, atol=1e-12)
        self.assertEqual(matrix_features(image).shape, (1024,))
        self.assertEqual(gasf(np.full(224, .5), "shape").shape, (224, 224))

    def test_windows_do_not_cross_run_or_include_outside_cf(self):
        first = pd.Series(np.full(230, .4))
        second = pd.Series(np.full(448, .6))
        first.iloc[100] = 1.2
        self.assertEqual(candidate_windows([first, second], 224, 224), [(1, 0), (1, 224)])
        np.testing.assert_array_equal(spread_indices(5, 3), [0, 2, 4])

    def test_end_to_end_with_temporary_segments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta = root / "metadata"
            meta.mkdir()
            manifests = []
            capacities = []
            metadata = []
            climate_map = []
            for i, farm in enumerate(("A", "B")):
                times = pd.date_range("2020-01-01", periods=224 * 3, freq="15min", tz="UTC")
                values = 0.4 + 0.25 * np.sin(np.arange(len(times)) / (9 + 3 * i))
                path = root / f"{farm}.csv"
                pd.DataFrame({"timestamp": times, "power": values}).to_csv(path, index=False)
                manifests.append({"name": farm, "source": "test", "layer": "aligned_segments", "segment_csv_path": str(path)})
                capacities.append({"name": farm, "source": "test", "rated_power_kW_used": 1000,
                                   "power_unit_original_csv": "MW", "rated_capacity_source": "rated"})
                metadata.append({"dataset_id": farm, "climate": f"C{i}", "source": "test",
                                 "site_type": "onshore", "rated_capacity_mw": 1})
                climate_map.append({"climate_original": f"C{i}", "climate_group": f"G{i}"})
            pd.DataFrame(manifests).to_csv(meta / "segments.csv", index=False)
            pd.DataFrame(capacities).to_csv(meta / "capacity.csv", index=False)
            pd.DataFrame(metadata).to_csv(meta / "farm_numeric_metadata.csv", index=False)
            pd.DataFrame(climate_map).to_csv(meta / "climate_groups.csv", index=False)
            (root / "publication.json").write_text(json.dumps({
                "metadata_dir": "metadata", "inputs": {"segments_manifest": "metadata/segments.csv",
                "capacity_table": "metadata/capacity.csv"}, "defaults": {"interval_minutes": 15}}))
            settings = root / "settings.json"
            settings.write_text(json.dumps({"publication_config": "publication.json", "window_points": 224,
                                             "stride_points": 224, "max_windows_per_farm": 3,
                                             "clusters": 2, "seed": 7, "farms": ["A", "B"]}))
            self.assertFalse(run(settings, root / "output", inspect=True)["raw_series_accessed"])
            report = run(settings, root / "output")
            self.assertEqual(report["windows"], 6)
            self.assertEqual(len(list((root / "output" / "images" / "fixed").rglob("*.png"))), 6)
            self.assertTrue((root / "output" / "shape" / "cluster_by_climate_group.csv").exists())


if __name__ == "__main__":
    unittest.main()
