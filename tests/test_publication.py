"""Tiny synthetic fixtures only. No researcher raw-power files are opened here."""
from pathlib import Path
import copy
import json
import subprocess
import sys
import tempfile
import unittest
import numpy as np
import pandas as pd
from wind_dataset_plot.config import DEFAULTS
from wind_dataset_plot.io import Dataset
from wind_dataset_plot.publication import ObservationCollector,climate_profiles,climate_metadata,main
from wind_dataset_plot.publication_plotting import daily_panels,volatility_scatter

class CollectorTests(unittest.TestCase):
    def series(self,values):return pd.Series(values,index=pd.date_range('2020-01-01',periods=len(values),freq='h',tz='UTC'))
    def test_pooled_is_hour_weighted_not_farm_mean_distribution(self):
        collector=ObservationCollector()
        for name,vals in [('A',[.1,.1,.1]),('B',[.9])]:
            collector(Dataset(name,capacity_kw=10000),[self.series(vals)],[self.series(vals)])
        density,stats=collector.density()
        self.assertAlmostEqual(stats['pooled_mean_cf'],.3)  # Equal-farm mean would be .5.
        self.assertEqual(int(density['count'].sum()),4)
        self.assertAlmostEqual(density.density.sum()/2000,1)

    def test_exact_endpoints_and_real_exceedance(self):
        c=ObservationCollector();s=self.series([0,1]);c(Dataset('A',capacity_kw=1000),[s],[s])
        self.assertEqual(c.density()[1]['complete_hour_count'],2)
        c=ObservationCollector();s=self.series([.2,1.01]);c(Dataset('A',capacity_kw=1000),[s],[s])
        self.assertEqual(c.audit[0]['raw_above_rated'],1)
        self.assertAlmostEqual(c.audit[0]['observed_max_mw'],1.01)
        with self.assertRaisesRegex(ValueError,'inconsistencies'):c.density()

    def test_raw_exceedance_not_hidden_by_hourly_averaging(self):
        c=ObservationCollector()
        c(Dataset('A',capacity_kw=1000),[self.series([.1,1.1])],[self.series([.6])])
        with self.assertRaises(ValueError):c.require_capacity_bounds()

    def test_climate_equal_farm_profiles(self):
        result={'summary':pd.DataFrame({'dataset_id':['A','B'],'climate_group':['Oceanic']*2}),
                'farm_hourly_profile':pd.DataFrame([[10.]*24,[90.]*24],index=['A','B'])}
        table=climate_profiles(result)
        np.testing.assert_allclose(table.median_cf,.5)
        np.testing.assert_allclose(table.q25_cf,.3)
        np.testing.assert_allclose(table.q75_cf,.7)

    def test_five_climate_facet_layout(self):
        md=Path(__file__).resolve().parents[1]/'inputs/revised_metadata'
        groups=sorted(pd.read_csv(md/'climate_groups.csv').climate_group.unique())
        table=pd.DataFrame([{'climate_group':g,'hour_utc':h,'median_cf':.5,'q25_cf':.3,'q75_cf':.7}
                            for g in groups for h in range(24)])
        with tempfile.TemporaryDirectory() as d:
            pdf=daily_panels({'climate_profiles':table},Path(d)/'test_only_climate_panels')
            self.assertTrue(Path(pdf).is_file())
            checker=Path(__file__).resolve().parents[1]/'tools/figure_qa/audit_figure_collisions.py'
            audit=subprocess.run([sys.executable,str(checker),str(pdf)],capture_output=True,text=True)
            self.assertEqual(audit.returncode,0,audit.stdout+audit.stderr)

class PublicationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.meta=self.root/'metadata';self.meta.mkdir()
        cfg=copy.deepcopy(DEFAULTS)
        cfg.update(data_dir=str(self.root),metadata_dir=str(self.meta),output_dir=str(self.root/'results'))
        cfg['defaults'].update(value_column='power',value_unit='MW',timestamp_position='instantaneous',timezone='UTC',interval_minutes=15)
        cfg['analysis'].update(clusters=2)
        segments=[];capacities=[];metadata=[];equipment=[]
        for i,site in enumerate(['onshore','offshore']):
            name=f'farm_{i}';path=self.root/f'{name}.csv';capacity=10+i*200
            t=np.arange(96*4)
            pd.DataFrame({'timestamp':pd.date_range('2020-01-01',periods=len(t),freq='15min'),
                          'power':capacity*(.35+.1*np.sin(t*np.pi/48+i)+.05*np.sin(t*np.pi/97))}).to_csv(path,index=False)
            segments.append([name,'fixture','aligned_segments',str(path)])
            capacities.append([name,'fixture',capacity*1000,capacity,'MW','xlsx_equipment_count_times_rated_kw',site])
            metadata.append([name,site,capacity,'Oceanic climate' if i else 'Cold semi-arid climate',False,'fixture'])
            equipment.append([name,site,'unit_group',100+i*20,90+i*10])
        pd.DataFrame(segments,columns=['name','source','layer','segment_csv_path']).to_csv(self.root/'segments.csv',index=False)
        pd.DataFrame(capacities,columns=['name','source','rated_power_kW_used','rated_power_MW_used','power_unit_original_csv','rated_capacity_source','onshore_offshore']).to_csv(self.root/'capacities.csv',index=False)
        pd.DataFrame(metadata,columns=['dataset_id','site_type','rated_capacity_mw','climate','is_virtual','source']).to_csv(self.meta/'farm_numeric_metadata.csv',index=False)
        pd.DataFrame(equipment,columns=['dataset_id','site_type','record_kind','rotor_m','hub_m']).to_csv(self.meta/'turbine_groups_long.csv',index=False)
        pd.DataFrame([['Oceanic climate','Oceanic'],['Cold semi-arid climate','Arid / semi-arid']],columns=['climate_original','climate_group']).to_csv(self.meta/'climate_groups.csv',index=False)
        cfg['inputs'].update(segments_manifest=str(self.root/'segments.csv'),capacity_table=str(self.root/'capacities.csv'))
        self.config=self.root/'config.json';self.config.write_text(json.dumps(cfg),encoding='utf-8')

    def tearDown(self):self.temp.cleanup()

    def test_metadata_only_does_not_read_raw(self):
        for path in self.root.glob('farm_*.csv'):path.unlink()
        self.assertEqual(main(['--config',str(self.config),'--metadata-only']),0)
        state=json.loads((self.root/'results/run_manifest.json').read_text())
        self.assertFalse(state['raw_series_accessed'])
        self.assertEqual(len(state['figures']),1)

    def test_unconfirmed_climate_mapping_blocks_before_raw_access(self):
        (self.meta/'climate_groups_status.json').write_text(json.dumps({'status':'awaiting_author_definition','required_groups':5}))
        for path in self.root.glob('farm_*.csv'):path.unlink()
        with self.assertRaisesRegex(ValueError,'author-defined five categories'):
            main(['--config',str(self.config)])
        self.assertFalse((self.root/'results').exists())

    def test_query_only_outputs_real_computed_fields_no_figures(self):
        self.assertEqual(main(['--config',str(self.config),'--query-only']),0)
        q=pd.read_csv(self.root/'results/tables/server_capacity_query.csv')
        self.assertEqual(len(q),2);self.assertTrue(q.capacity_consistent.all())
        self.assertFalse((self.root/'results/figures').exists())
        stats=pd.read_csv(self.root/'results/tables/farm_statistics.csv')
        self.assertTrue(stats.stl_weekly.isna().all())
        self.assertTrue((stats.mean_hourly_change_pp>0).all())

    def test_complete_seven_figure_export_from_synthetic_fixture(self):
        self.assertEqual(main(['--config',str(self.config)]),0)
        state=json.loads((self.root/'results/run_manifest.json').read_text())
        self.assertEqual(state['status'],'complete');self.assertEqual(len(state['figures']),7)
        for pdf in state['figures']:self.assertTrue(Path(pdf).is_file())
        self.assertEqual(state['pooled']['complete_hour_count'],192)
        daily=pd.read_csv(self.root/'results/tables/daily_profiles_index.csv')
        self.assertEqual(len(daily),8);self.assertTrue(daily.climate_group.notna().all())
        checker=Path(__file__).resolve().parents[1]/'tools/check_publication_figures.py'
        audit=subprocess.run([sys.executable,str(checker),str(self.root/'results')],capture_output=True,text=True)
        self.assertEqual(audit.returncode,0,audit.stdout+audit.stderr)

    def test_actual_metadata_climate_join_reads_no_series(self):
        repo=Path(__file__).resolve().parents[1]
        md=repo/'inputs/revised_metadata'
        farms=pd.read_csv(md/'farm_capacity_units_131_updated.csv')
        mapped=climate_metadata(md/'farm_numeric_metadata.csv',md/'climate_groups.csv',farms.name.tolist())
        self.assertEqual(len(mapped),131);self.assertEqual(mapped.climate_group.nunique(),5)
        self.assertEqual(set(mapped.climate_group),{'Humid continental','Arid / semi-arid','Humid subtropical','Oceanic','Other climates'})
        transitional=mapped[mapped.climate.str.contains('transitional',na=False)]
        self.assertTrue(transitional.climate_group.eq('Other climates').all())

if __name__=='__main__':unittest.main()
