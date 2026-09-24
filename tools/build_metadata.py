"""Parse the supplied equipment descriptions; never infer capacity from observed power."""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import json
import re
import numpy as np
import pandas as pd
import openpyxl

SOURCE_MAP = {'NREL WTK': 'nrel_wtk', 'ENTSOE': 'entsoe', 'AEMO': 'aemo', 'huaneng': 'huaneng'}
NUM = r'(?:\d+(?:\.\d+)?|NaN)'

def number(text):
    match = re.search(r'\d+(?:\.\d+)?', str(text))
    return float(match[0]) if match else None

def fmt(x):
    return '' if x is None or pd.isna(x) else f'{x:g}'

def coords(text):
    values = re.findall(r'-?\d+(?:\.\d+)?', str(text))
    return tuple(round(float(x), 4) for x in values[:2]) if len(values) >= 2 else None

def farm_stem(text):
    text = re.sub(r'^NREL_WTK_site\d+_', '', str(text))
    text = re.sub(r'_\d+(?:\.\d+)?MW_\d{4}-\d{4}$', '', text)
    return re.sub(r'[^a-z0-9]', '', text.lower())

def parse_equipment(text):
    """Return actual/virtual unit groups and separate fitted-model references."""
    is_virtual = 'virtual turbine' in text
    groups, references = [], []
    if is_virtual:
        count = int(re.match(r'(\d+)\s*×', text)[1])
        kw = float(re.search(r'([\d.]+)\s*kW rated', text)[1])
        hub = float(re.search(r'hub\s+([\d.]+)\s*m', text)[1])
        model = re.search(r'(IEC Class \d power curve|offshore power curve)', text)[1]
        groups.append(dict(model=model, count=count, rated_kw=kw, rotor_m=None,
                           blade_m=None, hub_m=hub, approximate_count=False,
                           rotor_approx=False, blade_approx=False, hub_approx=False,
                           basis='virtual_turbine'))
        rotor_text = text.split('fitted-model rotors: ', 1)[1].split(', blades:', 1)[0]
        blade_text = text.split(', blades: ', 1)[1].split(', hub', 1)[0]
        rotors, blades = rotor_text.split(';'), blade_text.split(';')
        if len(rotors) != len(blades):
            raise ValueError('Reference model/geometry alignment mismatch')
        for r, b in zip(rotors, blades):
            match = re.fullmatch(r'\s*(.*?)\s+([\d.]+)\s*m\s*', r)
            if not match:
                raise ValueError(f'Unparsed reference rotor: {r}')
            references.append(dict(model=match[1], count=None, rated_kw=None,
                                   rotor_m=float(match[2]), blade_m=number(b), hub_m=hub,
                                   approximate_count=False, rotor_approx=False,
                                   blade_approx='≈' in b, hub_approx=False,
                                   basis='fitted_model_reference'))
    else:
        for part in re.split(r';\s*(?=≈?\d+\s*×)', text):
            start = re.match(r'(≈?)(\d+)\s*×\s*(.*?)\s*\(', part)
            if not start:
                raise ValueError(f'Missing explicit turbine count: {part}')
            kw = re.search(r'([\d.]+)\s*kW rated', part)
            if not kw:
                raise ValueError(f'Missing unit rated power: {part}')
            geometry = {}
            for name in ['rotor', 'blade']:
                match = re.search(r'(≈?' + NUM + r')\s*m\s+' + name, part)
                if not match:
                    raise ValueError(f'Missing {name} field: {part}')
                geometry[name+'_m'] = number(match[1])
                geometry[name+'_approx'] = '≈' in match[1]
            hub = re.search(r',\s*([^,]+?)\s+hub\)', part)
            if not hub:
                raise ValueError(f'Missing hub field: {part}')
            groups.append(dict(model=start[3], count=int(start[2]), rated_kw=float(kw[1]),
                               approximate_count=bool(start[1]), hub_m=number(hub[1]),
                               hub_approx='≈' in hub[1] or 'derived' in hub[1],
                               basis='installed_turbine', **geometry))
    return groups, references

def dimension_fields(groups, field, reference=False):
    known = [g for g in groups if g[field] is not None]
    values = sorted({g[field] for g in known})
    counts = Counter()
    for g in known:
        if g['count'] is not None:
            counts[g[field]] += g['count']
    unknown_count = sum(g['count'] or 0 for g in groups if g[field] is None)
    pretty = []
    for v in values:
        approx = any(g.get(field.replace('_m', '_approx')) for g in known if g[field] == v)
        pretty.append(('≈' if approx else '') + fmt(v))
    count_labels=[f'{fmt(v)} m: {counts[v]}台' for v in values]
    if unknown_count:
        count_labels.append(f'未知尺寸: {unknown_count}台')
    return dict(values='; '.join(pretty), variants=len(values),
                counts='参考机型，未分配机组数' if reference else '; '.join(count_labels),
                unknown_turbines=unknown_count,
                minimum=min(values) if values else None, maximum=max(values) if values else None,
                weighted_mean=(sum(g[field]*g['count'] for g in known)/sum(g['count'] for g in known)
                               if known and not reference and sum(g['count'] for g in known) else None))

def match_manifest(name, location, capacity, old):
    exact = old[old['name'].eq(name)]
    if len(exact) == 1:
        return exact.iloc[0], 'exact_name'
    if location is not None:
        by_coord = old[[coords(x) == location for x in old.lat_lon]]
        if len(by_coord) == 1:
            return by_coord.iloc[0], 'coordinates'
    stem = farm_stem(name)
    by_name = old[old['name'].map(farm_stem).eq(stem)]
    if len(by_name) > 1:
        embedded = by_name.name.str.extract(r'_(\d+(?:\.\d+)?)MW_')[0].astype(float)
        by_name = by_name[np.isclose(embedded, capacity)]
    if len(by_name) == 1:
        return by_name.iloc[0], 'name_and_declared_size' if stem else 'name'
    if name == 'huaneng':
        return None, 'not_in_131_manifest'
    raise ValueError(f'Ambiguous or absent manifest match: {name}')

def build(workbook, old_capacity, output):
    output.mkdir(parents=True, exist_ok=True)
    book = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    raw = list(book.active.values)
    old = pd.read_csv(old_capacity, keep_default_na=False)
    clean, analytic, detail, comparisons = [], [], [], []
    for excel_row, row in enumerate(raw[1:], 2):
        if not row[1]:
            continue
        role, name, cadence, observations, source, site, loc, elevation, climate, text, climate_detail, *_ = row
        groups, references = parse_equipment(text)
        capacity = sum(g['count'] * g['rated_kw'] for g in groups) / 1000
        previous, match = match_manifest(name, coords(loc), capacity, old)
        identifier = previous['name'] if previous is not None else name
        approximate = any(g['approximate_count'] for g in groups)
        virtual = bool(references)
        parts = [f"{'≈' if g['approximate_count'] else ''}{g['count']}×{fmt(g['rated_kw']/1000)}" for g in groups]
        dimensions = {f: dimension_fields(references if virtual and f != 'hub_m' else groups, f,
                                         reference=virtual and f != 'hub_m')
                      for f in ['rotor_m','blade_m','hub_m']}
        common = {'dataset_id':identifier, 'farm_name':name, 'excel_row':excel_row,
                  'source':SOURCE_MAP[source], 'site_type':site.lower(), 'rated_capacity_mw':capacity,
                  'turbine_count':sum(g['count'] for g in groups), 'turbine_group_count':len(groups),
                  'capacity_approximate':approximate, 'is_virtual':virtual,
                  'in_manifest_131':previous is not None, 'match_method':match,
                  'capacity_group':'<50 MW' if capacity < 50 else ('50–150 MW' if capacity <= 150 else '>150 MW'),
                  'reference_model_count':len(references), 'capacity_formula_mw':' + '.join(parts),
                  'latitude':coords(loc)[0] if coords(loc) else None,
                  'longitude':coords(loc)[1] if coords(loc) else None, 'climate':climate}
        for f, d in dimensions.items():
            common.update({f'{f}_{k}':d[k] for k in ['minimum','maximum','weighted_mean','variants','unknown_turbines']})
        analytic.append(common)
        public = {'数据集标识':identifier,'风场名称':name,'数据粒度':cadence,'数据数量':observations,
                  '所属数据集':source,'Onshore/Offshore':site,'位置（纬度，经度）':loc,
                  '基座海拔':elevation,'气候类型':climate,'气候特点':climate_detail,
                  '风机型号':'; '.join(g['model'] for g in (references if virtual else groups)),
                  '参数性质':'虚拟机组及拟合参考机型' if virtual else '实际机组型号',
                  '机组总数':common['turbine_count'],'风场额定功率_MW':round(capacity,6),
                  '额定功率计算式_MW':' + '.join(parts),
                  '容量计算精度':'近似机组数' if approximate else '按表中机组数',
                  '参考机型数':len(references)}
        for f, label in [('rotor_m','叶轮直径'),('blade_m','叶片长'),('hub_m','轮毂高')]:
            d=dimensions[f]
            public.update({label+'_m':d['values'],label+'_规格数':d['variants'],
                           label+'_各规格机组数':d['counts']})
        clean.append(public)
        for kind, records in [('unit_group',groups),('reference_model',references)]:
            for j,g in enumerate(records,1):
                detail.append(dict(dataset_id=identifier,farm_name=name,record_kind=kind,group_index=j,
                                   source=SOURCE_MAP[source],site_type=site.lower(),excel_row=excel_row,**g))
        if previous is not None:
            before = float(previous['rated_power_MW_used'])
            comparisons.append(dict(name=identifier,old_capacity_mw=before,new_capacity_mw=capacity,
                                    difference_mw=capacity-before,changed=not np.isclose(before,capacity),
                                    old_basis=previous['rated_capacity_source'],
                                    new_basis='equipment_count_times_rated_power',approximate=approximate))
    farms = pd.DataFrame(analytic)
    if farms.dataset_id.duplicated().any():
        raise ValueError('Dataset IDs are not unique after matching')
    main = pd.DataFrame(clean)
    assert not {'角色','周边地貌','备注 (Notes)'}.intersection(main.columns)
    main.to_csv(output/'windfarm_metadata_clean.csv',index=False,encoding='utf-8-sig')
    main[farms.in_manifest_131.to_numpy()].to_csv(output/'windfarm_metadata_131.csv',index=False,encoding='utf-8-sig')
    farms.to_csv(output/'farm_numeric_metadata.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(detail).to_csv(output/'turbine_groups_long.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(comparisons).to_csv(output/'capacity_recalculation_audit.csv',index=False,encoding='utf-8-sig')
    updated = old.copy()
    lookup = farms.set_index('dataset_id')
    for i,r in updated.iterrows():
        f=lookup.loc[r['name']]
        updated.loc[i,'rated_power_kW_used']=f.rated_capacity_mw*1000
        updated.loc[i,'rated_power_MW_used']=f.rated_capacity_mw
        updated.loc[i,'onshore_offshore']=str(f.site_type).title()
        updated.loc[i,'rated_capacity_source']='xlsx_equipment_count_times_rated_kw'+('_approximate_count' if f.capacity_approximate else '')
    updated=updated[['name','source','rated_power_kW_used','rated_power_MW_used','power_unit_original_csv',
                     'rated_capacity_source','onshore_offshore']]
    updated.to_csv(output/'farm_capacity_units_131_updated.csv',index=False,encoding='utf-8-sig')
    report={'metadata_rows':len(farms),'matched_to_131':int(farms.in_manifest_131.sum()),
            'extra_metadata':farms.loc[~farms.in_manifest_131,'dataset_id'].tolist(),
            'changed_capacities':sum(r['changed'] for r in comparisons),
            'virtual_sites':int(farms.is_virtual.sum()),
            'approximate_capacities':farms.loc[farms.capacity_approximate,'dataset_id'].tolist(),
            'capacity_formula':'sum(turbine_count * unit_rated_kW) / 1000',
            'capacity_groups':'<50 MW; 50–150 MW inclusive; >150 MW',
            'reference_geometry':'NREL rotor/blade values are fitted-model references, not installed equipment',
            'missing_geometry':'Empty measurement fields remain missing; zero distinct known values means unavailable'}
    (output/'metadata_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return farms

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--workbook',required=True,type=Path)
    p.add_argument('--old-capacity',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    build(args.workbook,args.old_capacity,args.output)
