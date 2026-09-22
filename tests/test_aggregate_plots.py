"""Check aggregation semantics and absence of farm identity in published figures."""
import copy
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from examples.preview_aggregate import make_preview
from wind_dataset_plot.config import DEFAULTS
from wind_dataset_plot.plotting import plot_all, draw, quantile_envelopes


class AggregateTests(unittest.TestCase):
    def test_quantile_band_weights_farms_equally(self):
        frame=pd.DataFrame({"site_type":["offshore"]*3,"n_hourly":[1,10000,1]})
        for col in ("cf_p10","cf_p25","cf_median","cf_p75","cf_p90"):
            frame[col]=[0.,.6,1.]
        site,n,band=quantile_envelopes(frame)[0]
        self.assertEqual((site,n),("offshore",3))
        np.testing.assert_allclose(band,np.tile([[.3],[.6],[.8]],(1,5)))

    def test_131_farms_have_seven_figures_without_identity_or_pagination(self):
        with tempfile.TemporaryDirectory() as temporary:
            cfg=copy.deepcopy(DEFAULTS); cfg["output_dir"]=temporary
            cfg["plots"].update(formats=["svg"],rows_per_page=1,layout="legacy")
            result=make_preview(131)
            files=plot_all(result,cfg)
            self.assertEqual(len(files),7)
            self.assertTrue(any("figure5_corpus_diversity.svg" in p for p in files))
            for path in files:
                text=Path(path).read_text(encoding="utf-8")
                self.assertNotIn("PRIVATE_FARM",text)
                self.assertNotIn("Private farm",text)
                self.assertIn("SYNTHETIC STYLE PREVIEW",text)

    def test_seasonal_density_counts_valid_farms_once(self):
        result=make_preview(131)
        fig,ax=plt.subplots()
        try:
            draw("d",ax,result,DEFAULTS)
            n=result["summary"][["stl_daily","stl_weekly"]].notna().all(axis=1).sum()
            self.assertEqual(ax.collections[0].get_array().sum(),n)
            self.assertFalse(ax.texts)
        finally: plt.close(fig)

    def test_small_constant_missing_groups_and_single_site(self):
        result=make_preview(1)
        result["summary"]["stl_weekly"]=np.nan
        result["summary"]["ramp_p95"]=np.nan
        for panel in "abd":
            fig,ax=plt.subplots()
            try:
                draw(panel,ax,result,DEFAULTS)
                fig.canvas.draw()
                if panel=="d": self.assertTrue(any("No farms" in t.get_text() for t in ax.texts))
            finally: plt.close(fig)


if __name__=="__main__": unittest.main()
