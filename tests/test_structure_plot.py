from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from wind_dataset_plot.structure_plot import structure_summary,draw_structure,main


class StructureTests(unittest.TestCase):
    def frame(self,n=131):
        return pd.DataFrame(dict(dataset_id=[f"PRIVATE_FARM_{i}" for i in range(n)],
            site_type=["offshore" if i<31 else "onshore" for i in range(n)],
            cf_median=np.linspace(.1,.7,n),cf_iqr=np.linspace(.2,.5,n),
            ramp_p95=np.linspace(.01,.2,n),n_hourly=np.arange(1,n+1)*100))

    def test_summary_weights_each_farm_once_and_uses_physical_units(self):
        frame=self.frame(3); frame["cf_median"]=[.1,.4,.9]; frame["n_hourly"]=[1,1,100000]
        summary=structure_summary(frame)
        row=summary.loc[summary.metric.eq("cf_median")&summary.site_type.eq("offshore")].iloc[0]
        self.assertEqual(row.n_farms,3); self.assertAlmostEqual(row["median"],40)
        self.assertEqual(row.unit,"percent_of_capacity")

    def test_every_valid_farm_is_a_point_and_missing_is_metric_specific(self):
        frame=self.frame(); frame.loc[0,"ramp_p95"]=np.nan
        fig,axes=plt.subplots(1,3)
        try:
            draw_structure(axes,frame,"viridis")
            from matplotlib.collections import PathCollection
            counts=[sum(len(c.get_offsets()) for c in ax.collections if isinstance(c,PathCollection)) for ax in axes]
            self.assertEqual(counts,[131,131,130])
            for ax in axes:
                self.assertEqual([t.get_text() for t in ax.get_xticklabels()],["Offshore","Onshore"])
                self.assertFalse(ax.get_title(loc="left"))
                self.assertFalse(ax.texts)
        finally: plt.close(fig)

    def test_constant_single_and_missing_groups_do_not_invent_densities(self):
        frame=self.frame(1); frame["cf_median"]=0; frame["ramp_p95"]=np.nan
        fig,axes=plt.subplots(1,3)
        try:
            draw_structure(axes,frame,"plasma")
            from matplotlib.collections import PolyCollection
            self.assertFalse(any(isinstance(c,PolyCollection) for ax in axes for c in ax.collections))
            self.assertEqual(structure_summary(frame).iloc[0]["median"],0)
            self.assertTrue(any("No valid" in t.get_text() for t in axes[2].texts))
        finally: plt.close(fig)

    def test_duplicate_farms_cannot_be_treated_as_independent_segments(self):
        frame=self.frame(2); frame["dataset_id"]="same_farm"
        with self.assertRaisesRegex(ValueError,"one row per original farm"):
            structure_summary(frame)

    def test_standalone_summary_export_is_anonymous_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory); source=path/"dataset_summary.csv"; out=path/"plots"
            self.frame().to_csv(source,index=False)
            args=["--summary",str(source),"--output",str(out)]
            self.assertEqual(main(args),0)
            self.assertEqual(len(list((out/"figures").glob("*"))),3)
            self.assertNotIn("PRIVATE_FARM",(out/"figures/farm_structure_comparison.svg").read_text())
            self.assertTrue((out/"structure_summary.csv").is_file())
            with self.assertRaises(SystemExit): main(args)
