"""Equipment arithmetic and temporal invariants; fixtures are not research results."""
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_metadata import parse_equipment, dimension_fields
from wind_dataset_plot.config import load_config
from wind_dataset_plot.revised import size_group, derived_tables, prepare, main, embed_profiles
from wind_dataset_plot.analysis import analyze
import test_manifests

class EquipmentTests(unittest.TestCase):
    def test_umap_keeps_every_test_day_and_exports(self):
        import tempfile
        from wind_dataset_plot.revised_plotting import umap_panel
        vectors=np.array([.4+.1*np.sin(np.arange(24)*np.pi/12+j*.5)+j*.02 for j in range(8)])
        result=embed_profiles({'profiles':vectors,'daily':pd.DataFrame({'pattern':['P01']*4+['P02']*4})},42)
        self.assertEqual(len(result['daily']),8)
        self.assertTrue(np.isfinite(result['daily'][['umap_1','umap_2']]).all().all())
        with tempfile.TemporaryDirectory() as folder:
            pdf=umap_panel(result,Path(folder)/'test_only_umap')
            self.assertTrue(Path(pdf).is_file())

    def test_mixed_equipment_count_and_capacity(self):
        groups,_=parse_equipment('7 × Senvion MM92/2050 (2050 kW rated, 92.5 m rotor, ≈45.2 m blade, 80 m hub); 6 × Senvion MM82/2000 (2000 kW rated, 82 m rotor, 40 m blade, 80 m hub); 2 × Senvion MM82/2050 (2050 kW rated, 82 m rotor, 40 m blade, 80 m hub)')
        self.assertAlmostEqual(sum(g['count']*g['rated_kw'] for g in groups)/1000,30.45)
        self.assertEqual(dimension_fields(groups,'rotor_m')['counts'],'82 m: 8台; 92.5 m: 7台')
        self.assertEqual(dimension_fields(groups,'rotor_m')['variants'],2)

    def test_unknown_and_approximate_are_not_invented(self):
        groups,_=parse_equipment('29 × Enercon E70/2300 (2300 kW rated, 71 m rotor, NaN m blade, ≈69 m (derived) m hub)')
        self.assertIsNone(groups[0]['blade_m'])
        self.assertEqual(dimension_fields(groups,'blade_m')['unknown_turbines'],29)
        self.assertTrue(groups[0]['hub_approx'])
        groups,_=parse_equipment('≈47 × Siemens SWT-3.6-107 (3600 kW rated, 107 m rotor, 52 m blade, 78 m hub)')
        self.assertTrue(groups[0]['approximate_count'])
        self.assertAlmostEqual(groups[0]['count']*groups[0]['rated_kw']/1000,169.2)

    def test_virtual_capacity_excludes_reference_models(self):
        text='8 × virtual turbine (2000 kW rated, IEC Class 3 power curve, fitted-model rotors: Vestas V100-1.8 100 m; GE 1.6-100 100 m; REpower 3.2M114 114 m, blades: 48.7 m; ≈49 m; ≈55.5 m, hub 100 m)'
        groups,refs=parse_equipment(text)
        self.assertEqual(sum(g['count']*g['rated_kw'] for g in groups)/1000,16)
        self.assertEqual(len(refs),3)
        self.assertEqual(dimension_fields(refs,'rotor_m',True)['variants'],2)
        self.assertIsNone(dimension_fields(refs,'rotor_m',True)['weighted_mean'])
        self.assertTrue(all(g['count'] is None for g in refs))

    def test_capacity_boundaries(self):
        self.assertEqual([size_group(x) for x in [49.9,50,150,150.1]],
                         ['<50 MW','50–150 MW','50–150 MW','>150 MW'])
        for x in [0,-1,np.nan]:
            with self.assertRaises(ValueError):size_group(x)

    def test_daily_farm_weighting_and_pp_units(self):
        result={'summary':pd.DataFrame({'dataset_id':['A','B'],'capacity_kw':[10000,200000],
                    'site_type':['onshore','offshore'],'ramp_mean':[.05,.03],'ramp_p95':[.1,.07]}),
                'daily':pd.DataFrame({'dataset_id':['A','A','B']}),
                'profiles':np.array([[.1]*24,[.3]*24,[.6]*24])}
        result=derived_tables(result)
        np.testing.assert_allclose(result['farm_hourly_profile'].loc['A'],20)
        np.testing.assert_allclose(result['farm_hourly_profile'].loc['B'],60)
        np.testing.assert_allclose(result['summary'].mean_hourly_change_pp,[5,3])

    def test_real_manifest_inspection_without_series_access(self):
        root=Path(__file__).resolve().parents[1]
        farms,report=prepare(load_config(root/'revised_config.json'),access_files=False)
        self.assertEqual((len(farms),report['selected_segments']),(131,1770))
        self.assertEqual(report['capacity_proxy_farms'],[])
        caps={f['id']:f['capacity_kw']/1000 for f in farms}
        for name,value in [('CULLRGWF',30.45),('BRDUW-1',72),('SNOWNTH1',69),('SNOWSTH1',201)]:
            self.assertAlmostEqual(caps[name],value)

class RevisedManifestTests(test_manifests.ManifestTests):
    def test_all_revised_exports_with_explicit_umap_skip(self):
        import json
        self.cap['rated_capacity_source']='xlsx_equipment_count_times_rated_kw'
        self.write_tables()
        self.cfg['analysis']['clusters']=1
        self.assertEqual(main(['--config',str(self.config_file()),'--skip-umap']),0)
        manifest=json.loads((self.root/'results/run_manifest.json').read_text())
        self.assertTrue(manifest['figures_recomputed'])
        self.assertEqual(manifest['skipped_panels'],['original_e_umap'])
        self.assertEqual(len(manifest['figures']),5)
        for f in manifest['figures']: self.assertTrue(Path(f).is_file())
        import fitz
        for f in manifest['figures']:
            with fitz.open(f) as doc:
                self.assertEqual(len(doc),1)
                self.assertTrue(doc[0].get_text().strip())

    def test_revised_prepare_uses_capacity_and_site_without_json(self):
        self.cap['rated_capacity_source']='xlsx_equipment_count_times_rated_kw'
        self.write_tables()
        self.cfg['metadata_dir']=str(self.root/'no_json_needed')
        self.cfg['plots']['panels']=['b']
        datasets,_=prepare(self.cfg)
        result=derived_tables(analyze(datasets,self.cfg))
        self.assertEqual(len(result['summary']),2)
        np.testing.assert_allclose(result['summary'].cf_mean,.5)
        np.testing.assert_allclose(result['summary'].mean_hourly_change_pp,0)
        self.assertEqual(set(result['summary'].site_type),{'onshore','offshore'})
        self.assertEqual(result['summary'].set_index('dataset_id').n_segments.to_dict(),{'farm_1':2,'farm_2':1})

if __name__=='__main__': unittest.main()
