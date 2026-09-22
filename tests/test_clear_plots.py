"""Statistical denominators and display selection for the four-panel main figure."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from test_pipeline import Fixture
from wind_dataset_plot.analysis import output_fractions,analyze
from wind_dataset_plot.clear_plotting import group_output,draw_clear,monthly_coverage,daily_change_distribution
from wind_dataset_plot.cli import main


class ClearPlotTests(Fixture):
    def setUp(self):
        super().setUp()
        self.cfg["plots"]["layout"]="clear"

    def test_bins_preserve_extremes_and_endpoints(self):
        values=output_fractions([-1,0,.05,.95,1,2,np.nan])
        self.assertAlmostEqual(values.sum(),1)
        np.testing.assert_allclose(values[[0,1,10,11]],[1/6,2/6,2/6,1/6])

    def test_histogram_gives_farms_equal_weight(self):
        rows=[]
        for values in ([.05],np.full(1000,.95)):
            rows.append({"site_type":"offshore",**{f"output_fraction_{i:02}":v
                         for i,v in enumerate(output_fractions(values))}})
        site,n,values=group_output(pd.DataFrame(rows))[0]
        self.assertEqual((site,n),("offshore",2))
        np.testing.assert_allclose(values[[1,10]],[50,50])
        self.assertAlmostEqual(values.sum(),100)

    def test_hourly_mean_change_never_crosses_cut(self):
        self.segment("farm",0,[100,200,100],freq="1h")
        self.segment("farm",1,[800,900],start="2020-01-01 03:00",freq="1h")
        self.meta("farm"); self.cfg["plots"]["panels"]=["a","b"]
        result=analyze(self.datasets(),self.cfg)
        self.assertAlmostEqual(result["summary"].iloc[0].ramp_mean,.1)
        self.assertAlmostEqual(result["summary"].filter(like="output_fraction_").iloc[0].sum(),1)

    def test_main_a_has_curves_not_bars_and_c_shows_monthly_coverage(self):
        self.segment("farm",0,[100]*8); self.meta("farm")
        self.cfg["plots"]["panels"]=["a","c"]
        result=analyze(self.datasets(),self.cfg)
        fig,axes=plt.subplots(1,2)
        try:
            draw_clear("a",axes[0],result,self.cfg)
            self.assertEqual(len(axes[0].patches),0)
            self.assertGreater(len(axes[0].lines),0)
            draw_clear("c",axes[1],result,self.cfg)
            np.testing.assert_array_equal(axes[1].lines[0].get_ydata(),monthly_coverage(result["coverage"]).to_numpy())
            self.assertEqual(len(axes[1].images),0)
        finally: plt.close(fig)

    def test_daily_cdf_counts_ties_and_preserves_extreme_changes(self):
        result={"summary":pd.DataFrame({"site_type":["onshore"]}),
                "daily":pd.DataFrame({"mean_abs_hourly_ramp":[.1,.2,.2,1.2,np.nan]})}
        x,y=daily_change_distribution(result["daily"])
        np.testing.assert_allclose(x,[10,20,120])
        np.testing.assert_allclose(y,[25,75,100])
        fig,ax=plt.subplots()
        try:
            draw_clear("d",ax,result,self.cfg)
            np.testing.assert_allclose(ax.lines[0].get_ydata(),[0,25,75,100])
            self.assertGreaterEqual(ax.get_xlim()[1],120)
        finally: plt.close(fig)

    def test_monthly_coverage_keeps_zero_hours_and_partial_boundary_months(self):
        counts=pd.Series([2,0,0,4],index=pd.date_range("2020-01-31 22:00",periods=4,freq="1h",tz="UTC"))
        np.testing.assert_allclose(monthly_coverage(counts),[1,2])

    def test_constant_zero_daily_change_is_not_smoothed(self):
        daily=pd.DataFrame({"mean_abs_hourly_ramp":[0,0,0]})
        x,y=daily_change_distribution(daily)
        np.testing.assert_array_equal(x,[0]); np.testing.assert_array_equal(y,[100])

    def test_main_only_calculates_days_without_clustering_or_stl(self):
        self.segment("farm",0,500+np.sin(np.arange(96))*100,freq="1h"); self.meta("farm")
        self.cfg["plots"]["panels"]=list("abcd")
        result=analyze(self.datasets(),self.cfg)
        self.assertTrue(result["patterns"].empty)
        self.assertFalse(result["daily"].empty)
        self.assertTrue(result["summary"].stl_daily.isna().all())

    def test_clear_cli_exports_new_statistics_and_caption(self):
        self.segment("farm",0,np.tile(np.linspace(100,900,24),8),freq="1h"); self.meta("farm")
        self.cfg["plots"].update(panels=list("abcd"),formats=["png","pdf","svg"])
        self.assertEqual(main(["--config",str(self.config_file())]),0)
        out=Path(self.cfg["output_dir"])
        self.assertEqual(len(list((out/"figures").glob("*.pdf"))),5)
        self.assertTrue((out/"figures/figure5_clear.pdf").is_file())
        self.assertIn("Two output-frequency curves",(out/"figure_description.md").read_text())
        distribution=pd.read_csv(out/"tables/output_distribution.csv")
        self.assertAlmostEqual(distribution.mean_time_percent.sum(),100)
        self.assertTrue((out/"tables/coverage_monthly.csv").is_file())
        curve=pd.read_csv(out/"tables/daily_change_distribution.csv")
        self.assertEqual(curve.days_at_or_below_percent.iloc[-1],100)
        for p in (out/"figures").glob("*.svg"):
            self.assertNotIn("farm_seq",p.read_text())

    def test_missing_days_has_no_fabricated_curves(self):
        self.segment("farm",0,[100]*8); self.meta("farm")
        self.cfg["plots"]["panels"]=["d"]
        result=analyze(self.datasets(),self.cfg)
        fig,ax=plt.subplots()
        try:
            draw_clear("d",ax,result,self.cfg)
            self.assertEqual(len(ax.lines),0)
            self.assertTrue(any("No complete" in t.get_text() for t in ax.texts))
        finally: plt.close(fig)
