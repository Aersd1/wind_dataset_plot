"""Statistical denominators and display selection for the four-panel main figure."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from test_pipeline import Fixture
from wind_dataset_plot.analysis import output_fractions,analyze
from wind_dataset_plot.clear_plotting import group_output,draw_clear,monthly_coverage,group_monthly_output
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
        self.assertAlmostEqual(result["summary"].iloc[0].ramp_p95,.1)
        self.assertAlmostEqual(result["summary"].iloc[0].cf_median,.2)
        self.assertAlmostEqual(result["summary"].iloc[0].cf_iqr,.7)
        self.assertAlmostEqual(result["summary"].filter(like="output_fraction_").iloc[0].sum(),1)

    def test_main_a_preserves_denominator_and_c_shows_hourly_coverage(self):
        self.segment("farm",0,[100]*8); self.meta("farm")
        self.cfg["plots"]["panels"]=["a","c"]
        result=analyze(self.datasets(),self.cfg)
        # Tail observations remain in the frequency denominator and audit exports.
        fractions=np.zeros(12); fractions[[0,1,10,11]]=[.1,.2,.3,.4]
        result["summary"].loc[:,[f"output_fraction_{i:02}" for i in range(12)]]=fractions
        fig,axes=plt.subplots(1,2)
        try:
            draw_clear("a",axes[0],result,self.cfg)
            self.assertEqual(len(axes[0].patches),0)
            self.assertGreater(len(axes[0].lines),0)
            self.assertEqual(len(axes[0].collections),0)
            self.assertEqual(axes[0].get_xlim(),(0,100))
            self.assertAlmostEqual(axes[0].lines[0].get_ydata().sum(),50)
            draw_clear("c",axes[1],result,self.cfg)
            np.testing.assert_array_equal(axes[1].images[0].get_array()[:,0],result["coverage"].to_numpy())
            self.assertEqual(axes[1].yaxis.get_ticks_position(),"right")
            for ax in axes:
                self.assertFalse(ax.get_title(loc="left"))
                self.assertFalse(ax.texts)
        finally: plt.close(fig)

    def test_monthly_curve_weights_farms_equally_and_breaks_at_missing_month(self):
        rows=[]
        for value,hours in ((.1,1),(.9,1000)):
            rows.append({"site_type":"onshore",**{f"month_{m:02}_mean_cf":np.nan for m in range(1,13)},
                         "month_01_mean_cf":value,"month_01_hours":hours,"month_03_mean_cf":1.2})
        result={"summary":pd.DataFrame(rows)}
        grouped=group_monthly_output(result["summary"])
        onshore=grouped.loc[grouped.site_type.eq("onshore")].reset_index(drop=True)
        self.assertAlmostEqual(onshore.mean_output_percent.iloc[0],50)
        self.assertTrue(np.isnan(onshore.mean_output_percent.iloc[1]))
        np.testing.assert_array_equal(onshore.n_farms.iloc[:3],[2,0,2])
        fig,ax=plt.subplots()
        try:
            draw_clear("d",ax,result,self.cfg)
            np.testing.assert_allclose(ax.lines[0].get_ydata()[:3],[50,np.nan,120])
            self.assertGreaterEqual(ax.get_ylim()[1],120)
        finally: plt.close(fig)

    def test_monthly_coverage_keeps_zero_hours_and_partial_boundary_months(self):
        counts=pd.Series([2,0,0,4],index=pd.date_range("2020-01-31 22:00",periods=4,freq="1h",tz="UTC"))
        np.testing.assert_allclose(monthly_coverage(counts),[1,2])

    def test_zero_monthly_output_is_data_not_missing(self):
        frame=pd.DataFrame([{"site_type":"offshore",**{f"month_{m:02}_mean_cf":0. for m in range(1,13)}}])
        data=group_monthly_output(frame)
        np.testing.assert_array_equal(data.loc[data.site_type.eq("offshore"),"mean_output_percent"],np.zeros(12))
        self.assertTrue(data.loc[data.site_type.eq("onshore"),"mean_output_percent"].isna().all())

    def test_monthly_means_pool_same_calendar_month_across_years_and_segments(self):
        self.segment("farm",0,[100,300],start="2020-01-01",freq="1h")
        self.segment("farm",1,[900],start="2021-01-01",freq="1h")
        self.segment("farm",2,[500],start="2021-02-01",freq="1h")
        self.meta("farm"); self.cfg["plots"]["panels"]=["d"]
        row=analyze(self.datasets(),self.cfg)["summary"].iloc[0]
        self.assertAlmostEqual(row.month_01_mean_cf,1.3/3)
        self.assertEqual(row.month_01_hours,3)
        self.assertEqual(row.month_02_mean_cf,.5)
        self.assertTrue(np.isnan(row.month_03_mean_cf))

    def test_month_assignment_uses_configured_clock_timezone(self):
        self.segment("farm",0,[500,500],start="2020-01-01 01:00",freq="1h")
        self.meta("farm"); self.cfg["plots"]["panels"]=["d"]
        self.cfg["analysis"]["clock_timezone"]="America/New_York"
        row=analyze(self.datasets(),self.cfg)["summary"].iloc[0]
        self.assertEqual(row.month_12_hours,2)
        self.assertEqual(row.month_01_hours,0)

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
        self.assertEqual(len(list((out/"figures").glob("*.pdf"))),6)
        self.assertTrue((out/"figures/farm_structure_comparison.pdf").is_file())
        self.assertTrue((out/"tables/structure_summary.csv").is_file())
        self.assertTrue((out/"figures/figure5_clear.pdf").is_file())
        self.assertIn("Two output-frequency curves",(out/"figure_description.md").read_text())
        distribution=pd.read_csv(out/"tables/output_distribution.csv")
        self.assertAlmostEqual(distribution.mean_time_percent.sum(),100)
        self.assertTrue((out/"tables/coverage_monthly.csv").is_file())
        monthly=pd.read_csv(out/"tables/monthly_output.csv")
        self.assertEqual(len(monthly),24)
        self.assertEqual(monthly.n_farms.sum(),1)
        for p in (out/"figures").glob("*.svg"):
            svg=p.read_text()
            self.assertNotIn("farm_seq",svg)
            for unwanted in ("(n=","Each point:","One point =", "paired farms"):
                self.assertNotIn(unwanted,svg)

    def test_monthly_output_does_not_require_complete_days(self):
        self.segment("farm",0,[100]*8); self.meta("farm")
        self.cfg["plots"]["panels"]=["d"]
        result=analyze(self.datasets(),self.cfg)
        fig,ax=plt.subplots()
        try:
            draw_clear("d",ax,result,self.cfg)
            self.assertEqual(len(ax.lines),1)
            self.assertAlmostEqual(ax.lines[0].get_ydata()[0],10)
            self.assertTrue(np.isnan(ax.lines[0].get_ydata()[1:]).all())
        finally: plt.close(fig)
