"""Offline joint-scale audit over human references, training strata and stimuli.

No labels/SR enter scoring. Total NM SR is used only to select a small training
cohort. Synthetic clock/amplitude changes are not human-labelled difficulty
bands. All outputs are diagnostics; no calibration fitting or release.
"""
from __future__ import annotations
import argparse,hashlib,json,math,statistics,sys
from dataclasses import replace
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'src')]
from map_demand_v01 import control_vector_v01 as control
from map_demand_v01 import flow_execution_v02 as flow
from map_demand_v01.joint_validation_v01 import evaluate,evaluate_growth
from map_demand_v01.mod_context_v01 import normalize_mods
from map_demand_v01.mod_transform_v01 import transform_beatmap,scale_local_difficulty_windows
from map_demand_v01.osu_db_star_scale import read_nm_star_distribution
from osu_skill_profiler.parser.osu_parser import parse_osu_file,parse_osu
from osu_skill_profiler.signals.extractor import LocalSignalExtractor

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sha(p):return 'sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()

def rows_for(beatmap,mods):
    if 'ApproachRate' not in beatmap.difficulty:
        od=beatmap.difficulty.get('OverallDifficulty')
        if isinstance(od,(int,float)) and math.isfinite(od):beatmap=replace(beatmap,difficulty={**beatmap.difficulty,'ApproachRate':float(od)})
    context=normalize_mods(mods)
    beatmap,transform=transform_beatmap(beatmap,context)
    if not transform.get('analysis_ready'):raise ValueError('Unsupported transform')
    rows=LocalSignalExtractor('0.4.0')._extract_rows(beatmap)
    rows=scale_local_difficulty_windows(rows,transform.get('clock_rate',1.))
    for r,obj in zip(rows,beatmap.hit_objects):r.update({'v091.start_x_px':float(obj.x),'v091.start_y_px':float(obj.y)})
    preempts=[r['ls.preempt_ms'] for r in rows if r.get('ls.preempt_ms') is not None]
    return rows,dict(cs=beatmap.difficulty.get('CircleSize'),preempt=statistics.median(preempts) if preempts else None,
        mods=context['effective_mods'],rate=transform.get('clock_rate',1.))

def measures(rows,ctx):
    f=flow.extract_flow_measure(rows,ctx['mods'],circle_size=ctx['cs'],resolved_preempt_ms=ctx['preempt'])
    c=control.extract_control_measure(rows,ctx['mods'],resolved_preempt_ms=ctx['preempt'])
    return dict(flow_aim=f['value'],aim_control=c['value'],
        flow_peak=f['winning_section'],control_peak=c['winning_section'],
        flow_status=f['status'],control_status=c['status'])

def training_selection(songs,db_path,per_band):
    split_path=ROOT/'training/datasets/splits/v02/strict_disjoint.jsonl'
    train={}
    for line in split_path.open(encoding='utf-8'):
        r=json.loads(line)
        if r['split']=='train':train[r['map_checksum']]=r['set_group_key']
    qa_path=ROOT/'training/datasets/feature_qa_v02/feature_qa_20k.jsonl'
    qa={}
    for line in qa_path.open(encoding='utf-8'):
        r=json.loads(line)
        if r['checksum'] in train and not r.get('error'):qa[r['checksum']]=r.get('slider_ratio')
    db=read_nm_star_distribution(db_path)
    star_lookup=db['relative_path_to_nm_stars']
    bands=[('low',0.,4.),('middle',4.,6.),('high',6.,8.),('very_high',8.,math.inf)]
    buckets={name:[] for name,_,_ in bands}
    manifest=ROOT/'training/datasets/std_manifest.json'
    for line in manifest.open(encoding='utf-8'):
        if '"relative_path"' not in line:continue
        r=json.loads(line.rstrip().rstrip(','));checksum=r['checksum']
        if checksum not in qa:continue
        relative=r['relative_path'];sr=star_lookup.get(relative.replace('\\','/').casefold())
        if sr is None or sr<=0:continue
        band=next(name for name,lo,hi in bands if lo<=sr<hi)
        buckets[band].append(dict(key=str(r['beatmap_id'])+'-NM' if r.get('beatmap_id') else checksum[-12:]+'-NM',
            label=r['title']+' ['+r['version']+']',mods=[],path=str(songs/relative),checksum=checksum,
            band=band,nm_sr_sampling_only=sr,set_group=train[checksum],slider_ratio=qa[checksum],human_label=None))
    selected=[];sets=set();counts={}
    for name,_,_ in bands:
        candidates=sorted(buckets[name],key=lambda r:hashlib.sha256(('joint-review-v1:'+r['checksum']).encode()).hexdigest())
        # Alternate lower/higher slider shares for coverage, not a type label.
        strata=[[r for r in candidates if (r['slider_ratio'] or 0)<.35],
                [r for r in candidates if (r['slider_ratio'] or 0)>=.35]]
        interleaved=[]
        for i in range(max(map(len,strata),default=0)):
            interleaved.extend(s[i] for s in strata if i<len(s))
        count=0
        for r in interleaved:
            if r['set_group'] in sets:continue
            path=Path(r['path'])
            if not path.exists() or sha(path)!=r['checksum']:continue
            md5=hashlib.md5(path.read_bytes()).hexdigest()
            if md5 not in db['md5_to_nm_stars']:continue
            r['nm_sr_sampling_only']=db['md5_to_nm_stars'][md5]
            actual=next(n for n,lo,hi in bands if lo<=r['nm_sr_sampling_only']<hi)
            if actual!=name:continue
            selected.append(r);sets.add(r['set_group']);count+=1
            if count==per_band:break
        counts[name]=dict(eligible=len(candidates),selected=count)
    return selected,dict(counts=counts,bands=[dict(name=n,lower=lo,upper=None if math.isinf(hi) else hi) for n,lo,hi in bands],
        split_sha256=sha(split_path),qa_sha256=sha(qa_path),database_sha256=db['database_sha256'],
        stars_used_only_for_sampling=True,unique_set_groups=True,selection='strict train + existing 20k QA, deterministic checksum order, slider-share strata',
        human_accuracy_not_measured=True)

def synthetic_case(distance,interval,count=64,turn=45.,cs=4.):
    theta=math.radians(turn);radius=distance/(2*math.sin(theta/2))
    points=[(256+radius*math.cos(i*theta),192+radius*math.sin(i*theta)) for i in range(count+1)]
    if any(not (0<=x<=512 and 0<=y<=384) for x,y in points):raise ValueError('Stimulus leaves playfield')
    objects='\n'.join(f'{x:.12g},{y:.12g},{1000+i*interval:.12g},1,0' for i,(x,y) in enumerate(points))
    raw=f'osu file format v14\n[General]\nMode:0\n[Metadata]\nTitle:Joint scale stimulus\nArtist:Diagnostic\nCreator:Diagnostic\nVersion:Unlabelled\n[Difficulty]\nCircleSize:{cs}\nApproachRate:9\nOverallDifficulty:8\nSliderMultiplier:1.4\nSliderTickRate:2\n[TimingPoints]\n0,400,4,2,1,100,1,0\n[HitObjects]\n'+objects
    rows,ctx=rows_for(parse_osu(raw),[])
    return dict(distance_px=distance,interval_ms=interval,movement_count=count,turn_deg=turn,cs=cs,
        duration_ms=count*interval,human_label=None,**measures(rows,ctx))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--songs',type=Path,default=Path('G:/osu! 20210821/Songs'))
    p.add_argument('--db',type=Path,default=Path('G:/osu! 20210821/osu!.db'))
    p.add_argument('--per-band',type=int,default=6)
    args=p.parse_args()
    if args.per_band<1:p.error('--per-band must be positive')
    out=args.out.resolve();out.mkdir(exist_ok=False,parents=True)
    constraints=read(ROOT/'docs/flow-control-joint-constraints-2026-09-05.json');write(out/'constraints.json',constraints)
    sources={str(p.relative_to(ROOT)):sha(p) for pattern in ('flow_*.py','control_*.py','joint_validation_v01.py') for p in (ROOT/'tools/map_demand_v01').glob(pattern)}
    sources[str(Path(__file__).relative_to(ROOT))]=sha(__file__)
    write(out/'source-hashes.json',sources)
    keys={c['key'] for c in constraints['numeric']}|{r[x]['key'] for r in constraints['relations'] for x in ('left','right')}|{c['key'] for c in constraints['local_labels']}|{'4572837-HD'}
    entries=[r for r in read(ROOT/'tmp/flow-control-lab-r3-20260905/report.json')['results'] if r['key'] in keys]
    missing=keys-{entry['key'] for entry in entries}
    if missing:raise ValueError('Missing reference source: '+', '.join(sorted(missing)))
    known=[];local=[]
    for entry in entries:
        assert sha(entry['path'])==entry['checksum']
        rows,ctx=rows_for(parse_osu_file(entry['path']),entry['mods'])
        result=dict(key=entry['key'],label=entry['label'],checksum=entry['checksum'],mods=entry['mods'],**measures(rows,ctx))
        known.append(result);print('REFERENCE',result['key'],round(result['flow_aim'],3),round(result['aim_control'],3),flush=True)
        for label in constraints['local_labels']:
            if label['key']!=entry['key']:continue
            excerpt=[row for row in rows if label['start_ms']<=row['ls.start_time_ms']<=label['end_ms']]
            local.append({**label,'checksum':entry['checksum'],'object_count':len(excerpt),
                'scope':'Standalone excerpt; outside context excluded; no local numeric target inferred',**measures(excerpt,ctx)})
    write(out/'references.json',known)
    write(out/'local-reference-results.json',local)
    pred={r['key']:dict(flow_aim=r['flow_aim'],aim_control=r['aim_control']) for r in known}
    write(out/'human-constraint-results.json',{'current_implementation':evaluate(pred,constraints)})
    chosen,meta=training_selection(args.songs,args.db,args.per_band)
    write(out/'training-selection.json',dict(metadata=meta,entries=chosen));print('SELECTED',meta['counts'],flush=True)
    cohort=[]
    for i,entry in enumerate(chosen,1):
        rows,ctx=rows_for(parse_osu_file(entry['path']),[])
        result={**entry,**measures(rows,ctx)};cohort.append(result)
        print('TRAIN',i,entry['band'],entry['key'],round(result['flow_aim'] or 0,3),round(result['aim_control'] or 0,3),flush=True)
    write(out/'training-results.json',cohort)
    settings={(d,t,64,45.,4.) for d in (24.,60.,100.) for t in (40.,75.,100.,150.,240.)}
    settings|={(d,100.,n,45.,4.) for d in (24.,100.) for n in (16,32,64,128)}
    settings|={(60.,100.,64,45.,cs) for cs in (3.,4.,6.)}
    settings|={(60.,100.,64,angle,4.) for angle in (30.,45.,60.,75.)}
    stimuli=[]
    for values in sorted(settings):stimuli.append(synthetic_case(*values))
    write(out/'controlled-stimuli.json',dict(scope='Unlabelled geometry counterfactuals; not actual mods or total-SR strata',results=stimuli))
    write(out/'controlled-growth-results.json',evaluate_growth(stimuli))
    assert all(sha(ROOT/p)==digest for p,digest in sources.items())
    print('DONE',len(known),'human-reference maps',len(cohort),'unlabelled training maps',len(stimuli),'controlled stimuli',flush=True)

if __name__=='__main__':main()
