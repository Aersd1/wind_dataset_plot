"""Only synthetic tiny fixtures; no user research dataset is analyzed by the tests."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
import pandas as pd

from wind_dataset_plot.config import DEFAULTS,load_config
from wind_dataset_plot.io import (Dataset,discover,resolve_metadata,metadata_fields,normalize_unit,
                                  load_runs,to_cf,parse_time,source_stem)
from wind_dataset_plot.analysis import (hourly_runs,daily_profiles,seasonal_strength,analyze,
                                        cluster_profiles)
from wind_dataset_plot.cli import main
from wind_dataset_plot.plotting import plot_all


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/"raw").mkdir(); (self.root/"meta").mkdir()
        self.cfg=copy.deepcopy(DEFAULTS)
        self.cfg.update(data_dir=str(self.root/"raw"),metadata_dir=str(self.root/"meta"),output_dir=str(self.root/"results"))
        self.cfg["defaults"]["value_unit"]="kW"
        self.cfg["plots"].update(formats=["png"],dpi=90)
        self.cfg["analysis"].update(clusters=2)

    def tearDown(self): self.temp.cleanup()

    def segment(self,name,number,values,start="2020-01-01",freq="15min",source=None,header=True,times=None):
        folder=self.root/"raw"/(name+"_seq"); folder.mkdir(exist_ok=True)
        path=folder/f"{name}_{number}.csv"
        dates=pd.date_range(start,periods=len(values),freq=freq) if times is None else times
        with path.open("w",encoding="utf-8") as f:
            if header: f.write(f"# source: {source or '/original/'+name+'.csv'}\n# segment: {number}\n# range: [0, {len(values)})\n")
            pd.DataFrame({"timestamp":dates,"power":values}).to_csv(f,index=False)
        return path

    def meta(self,name,site="onshore",capacity=1000):
        path=self.root/"meta"/(name+".json")
        path.write_text(json.dumps({"dataset_name":name,"site_type":site,"rated_capacity_kw":capacity}),encoding="utf-8")
        return path

    def datasets(self):
        ds,_=discover(self.cfg)
        return resolve_metadata(ds,self.cfg)

    def config_file(self):
        p=self.root/"config.json"; p.write_text(json.dumps(self.cfg),encoding="utf-8"); return p


class IdentityTests(Fixture):
    def test_remover_source_counts_once_and_preserves_numeric_farm_name(self):
        self.segment("farm_1",0,[1,2,3,4]); self.segment("farm_1",1,[4,5,6,7],start="2020-02-01")
        self.segment("farm_2",0,[1,2,3,4]); self.meta("farm_1"); self.meta("farm_2","offshore")
        pd.DataFrame({"time":[1],"value":[2]}).to_csv(self.root/"raw"/"farm_1.csv",index=False)
        ds,ignored=discover(self.cfg)
        self.assertEqual([(d.id,len(d.files)) for d in ds],[("farm_1",2),("farm_2",1)])
        self.assertEqual(ignored,["farm_1.csv"])

    def test_parent_fallback_only_in_confirmed_seq_folder(self):
        self.segment("unit_12",0,[1,2],header=False)
        ds,_=discover(self.cfg); self.assertEqual(ds[0].id,"unit_12")
        self.assertEqual(source_stem(r"C:\raw\unit_12.csv"),"unit_12")

    def test_same_basename_different_sources_fails(self):
        self.segment("farm",0,[1,2],source="/a/farm.csv")
        self.segment("farm",1,[1,2],source="/b/farm.csv")
        with self.assertRaisesRegex(ValueError,"collision"): discover(self.cfg)

    def test_plain_and_segment_not_double_counted(self):
        self.segment("farm",0,[1,2])
        pd.DataFrame({"time":[1],"value":[2]}).to_csv(self.root/"raw"/"farm.csv",index=False)
        self.cfg["segments_only"]=False
        with self.assertRaisesRegex(ValueError,"both original"): discover(self.cfg)

    def test_metadata_text_does_not_misclassify_environment(self):
        result=metadata_fields({"farm_description":"Power from an onshore wind farm. Low roughness offshore. Summing to roughly 17.5 MW of rated capacity."})
        self.assertEqual(result["site_type"],"onshore"); self.assertEqual(result["capacity_kw"],17500)
        self.assertIsNone(result["value_unit"])

    def test_conflicting_window_jsons_fail(self):
        self.segment("farm",0,[1,2]); self.meta("farm")
        (self.root/"meta"/"farm_000001.json").write_text(json.dumps({"site_type":"offshore"}),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"conflicting"): self.datasets()

    def test_missing_unit_is_not_guessed_from_column_name(self):
        self.segment("farm",0,[1,2]); self.meta("farm"); self.cfg["defaults"]["value_unit"]=None
        with self.assertRaisesRegex(ValueError,"value_unit"): self.datasets()

    def test_metadata_history_is_never_used(self):
        self.segment("farm",0,[100,200,300,400]); path=self.meta("farm")
        obj=json.loads(path.read_text()); obj["history"]=[{"value":999999999}]; obj["statistics"]={"farm_mean":999999}
        path.write_text(json.dumps(obj))
        runs,_,_,_=load_runs(self.datasets()[0]); np.testing.assert_allclose(runs[0],[.1,.2,.3,.4])


class TimeSeriesTests(Fixture):
    def test_power_energy_unit_conversions(self):
        np.testing.assert_allclose(to_cf([250],"kW",1000,15),[.25])
        np.testing.assert_allclose(to_cf([.25],"MW",1000,15),[.25])
        np.testing.assert_allclose(to_cf([62.5],"kWh",1000,15),[.25])
        np.testing.assert_allclose(to_cf([.0625],"MWh",1000,15),[.25])

    def test_ramps_exclude_cut_boundary(self):
        self.segment("farm",0,[100]*8,start="2020-01-01 00:00")
        self.segment("farm",1,[900]*8,start="2020-01-01 03:00"); self.meta("farm")
        self.cfg["plots"]["panels"]=["a"]
        result=analyze(self.datasets(),self.cfg)
        self.assertEqual(result["summary"].iloc[0].ramp_p95,0)

    def test_mixed_sampling_cadence_rejected(self):
        self.segment("farm",0,[100]*8,freq="15min")
        self.segment("farm",1,[100]*4,start="2020-02-01",freq="10min"); self.meta("farm")
        with self.assertRaisesRegex(ValueError,"mixed cadence"): load_runs(self.datasets()[0])

    def test_zero_capacity_override_rejected(self):
        self.segment("farm",0,[100]*8); self.meta("farm")
        self.cfg["defaults"]["rated_capacity_kw"]=0
        with self.assertRaisesRegex(ValueError,"positive"): self.datasets()

    def test_gaps_and_file_boundaries_not_bridged(self):
        # Two half-hours from separate cut files must not become one complete hour.
        self.segment("farm",0,[100,100],start="2020-01-01 00:00")
        self.segment("farm",1,[900,900],start="2020-01-01 00:30")
        self.meta("farm")
        runs,step,_,_=load_runs(self.datasets()[0]); self.assertEqual(len(runs),2)
        self.assertEqual(hourly_runs(runs,step),[])

    def test_internal_missing_value_splits_run(self):
        self.segment("farm",0,[100,100,np.nan,900,900]); self.meta("farm")
        runs,_,audit,_=load_runs(self.datasets()[0]); self.assertEqual([len(x) for x in runs],[2,2])
        self.assertEqual(audit["invalid_values"],1)

    def test_identical_overlap_removed_conflicting_overlap_fails(self):
        self.segment("farm",0,[100,200,300,400])
        self.segment("farm",1,[300,400,500,600],start="2020-01-01 00:30"); self.meta("farm")
        runs,_,audit,_=load_runs(self.datasets()[0])
        self.assertEqual(sum(map(len,runs)),6); self.assertEqual(audit["duplicate_rows_removed"],2)
        self.segment("farm",1,[333,400,500,600],start="2020-01-01 00:30")
        with self.assertRaisesRegex(ValueError,"conflicting overlapping"): load_runs(self.datasets()[0])

    def test_out_of_range_values_are_preserved_and_audited(self):
        self.segment("farm",0,[-10,1200]); self.meta("farm")
        runs,_,audit,_=load_runs(self.datasets()[0]); self.assertEqual(audit["cf_outside_0_1"],2)
        np.testing.assert_allclose(runs[0],[-.01,1.2])

    def test_complete_day_requires_one_contiguous_run(self):
        self.segment("farm",0,np.ones(48)*100)
        self.segment("farm",1,np.ones(48)*100,start="2020-01-01 12:00"); self.meta("farm")
        runs,step,_,_=load_runs(self.datasets()[0]); hourly=hourly_runs(runs,step)
        profiles,_=daily_profiles(hourly,"UTC"); self.assertEqual(len(profiles),0)

    def test_complete_day_and_timestamp_end(self):
        self.segment("farm",0,np.ones(96)*100,start="2020-01-01 00:15"); self.meta("farm")
        self.cfg["defaults"]["timestamp_position"]="end"
        runs,step,_,_=load_runs(self.datasets()[0]); hourly=hourly_runs(runs,step)
        self.assertEqual(step,15*60*10**9)
        profiles,dates=daily_profiles(hourly,"UTC"); self.assertEqual(profiles.shape,(1,24))
        self.assertTrue(dates[0].startswith("2020-01-01"))

    def test_ambiguous_date_rejected_explicit_format_works(self):
        dates=pd.Series(["18/01/01 00:00","18/01/01 00:15"])
        with self.assertRaisesRegex(ValueError,"Ambiguous"): parse_time(dates,self.cfg["defaults"])
        opts={**self.cfg["defaults"],"timestamp_format":"%y/%m/%d %H:%M"}
        self.assertEqual(parse_time(dates,opts)[0].year,2018)

    def test_dst_day_excluded(self):
        times=pd.date_range("2020-03-08 05:00",periods=23,freq="1h",tz="UTC")
        vectors,_=daily_profiles([pd.Series(np.ones(23),index=times)],"America/New_York")
        self.assertEqual(len(vectors),0)

    def test_coverage_counts_original_datasets_once_and_keeps_gap(self):
        self.segment("farm",0,np.ones(4)*100,start="2020-01-01 00:00")
        self.segment("farm",1,np.ones(4)*100,start="2020-01-01 02:00")
        self.meta("farm"); self.cfg["plots"]["panels"]=["c"]
        r=analyze(self.datasets(),self.cfg)
        self.assertEqual(r["coverage"].tolist(),[1,0,1]); self.assertEqual(len(r["summary"]),1)

    def test_seasonality_periodic_and_insufficient(self):
        t=np.arange(24*24); values=.5+.2*np.sin(t*2*np.pi/24)
        series=pd.Series(values,index=pd.date_range("2020-01-01",periods=len(t),freq="1h",tz="UTC"))
        score,n,used,_=seasonal_strength([series],24,self.cfg["analysis"])
        self.assertGreater(score,.95); self.assertEqual(n,1); self.assertEqual(used,len(t))
        score,*_=seasonal_strength([series.iloc[:48]],168,self.cfg["analysis"])
        self.assertTrue(np.isnan(score))


class ClusteringTests(Fixture):
    def test_dynamic_k_single_and_empty(self):
        opts=self.cfg["analysis"]
        labels,summary,median,_=cluster_profiles(np.ones((6,24))*.3,opts)
        self.assertEqual(len(summary),1); self.assertEqual(median.shape,(1,24))
        self.assertAlmostEqual(summary["share"].sum(),1)
        self.assertEqual(len(cluster_profiles(np.empty((0,24)),opts)[1]),0)

    def test_clustering_uses_data_and_is_reproducible(self):
        rng=np.random.default_rng(1)
        profiles=np.r_[rng.normal(.1,.01,(12,24)),rng.normal(.8,.01,(12,24))]
        opts={**self.cfg["analysis"],"clusters":"auto","max_clusters":3}
        first=cluster_profiles(profiles,opts); second=cluster_profiles(profiles,opts)
        np.testing.assert_array_equal(first[0],second[0]); self.assertEqual(len(first[1]),2)
        self.assertAlmostEqual(first[1]["share"].sum(),1)


class EndToEndTests(Fixture):
    def make_data(self):
        t=np.arange(24*24)
        self.segment("farm_1",0,400+200*np.sin(t*2*np.pi/24)+40*np.cos(t*2*np.pi/168),freq="1h")
        t2=np.arange(24*8)
        self.segment("farm_1",1,200+100*np.sin(t2*2*np.pi/24),start="2020-02-01",freq="1h")
        self.segment("farm_2",0,650+200*np.cos(t*2*np.pi/24),freq="1h")
        self.meta("farm_1"); self.meta("farm_2","offshore")

    def test_validate_only_does_not_create_output(self):
        self.make_data(); result=main(["--config",str(self.config_file()),"--validate-only"])
        self.assertEqual(result,0); self.assertFalse(Path(self.cfg["output_dir"]).exists())

    def test_full_synthetic_pipeline_all_panels_and_formats(self):
        self.make_data(); self.cfg["plots"]["formats"]=["png","pdf","svg"]
        keep=os.environ.get("WIND_PLOT_SMOKE_DIR")
        if keep: self.cfg["output_dir"]=str(Path(keep).resolve())
        result=main(["--config",str(self.config_file()),"--overwrite"])
        out=Path(self.cfg["output_dir"])
        self.assertEqual(result,0)
        summary=pd.read_csv(out/"tables/dataset_summary.csv")
        self.assertEqual(len(summary),2); self.assertEqual(summary.n_segments.sum(),3)
        self.assertEqual(len(list((out/"figures").glob("*.png"))),7)
        self.assertEqual(len(list((out/"figures").glob("*.svg"))),7)
        self.assertEqual(len(list((out/"figures").glob("*.pdf"))),7)
        self.assertAlmostEqual(pd.read_csv(out/"tables/pattern_summary.csv")["share"].sum(),1)
        self.assertTrue((out/"run_manifest.json").is_file())

    def test_plasma_pagination(self):
        self.make_data(); self.cfg["palette"]="plasma"
        self.cfg["plots"].update(panels=["a","b","d"],rows_per_page=1,combined=False)
        results=analyze(self.datasets(),self.cfg)
        outputs=plot_all(results,self.cfg)
        self.assertEqual(len(outputs),6)

    def test_missing_days_draws_placeholder_not_fake_patterns(self):
        self.segment("farm",0,[100]*8); self.meta("farm")
        self.cfg["plots"].update(panels=["e","f"],combined=False)
        results=analyze(self.datasets(),self.cfg)
        self.assertTrue(results["patterns"].empty)
        self.assertEqual(len(plot_all(results,self.cfg)),2)


if __name__=="__main__": unittest.main()
