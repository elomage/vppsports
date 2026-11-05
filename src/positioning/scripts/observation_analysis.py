"""Read message cadence and both antennas' compressed observations without exporting files."""
import csv
import math
import struct
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

NAMES={138:'OBSVMCMPB',139:'OBSVHCMPB',240:'BESTNAVXYZB',242:'BESTNAVXYZHB',2118:'BESTNAVB',2119:'BESTNAVHB',972:'UNIHEADINGB',106:'GPSEPHB',107:'GLOEPHB',108:'BDSEPHB',109:'GALEPHB'}
PERIODIC={138,139,240,242,2118,2119,972}

def read_index(folder):
    path=folder/'csv/records_index.csv'
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def stamp(row):
    try:
        d=datetime.fromisoformat(row['utc'].replace('Z','+00:00'))
        return d.timestamp() if d.year>=2000 else None
    except (ValueError,KeyError):
        return None

def stream_summary(folder,bounds=None):
    grouped=defaultdict(list)
    for r in read_index(folder):
        t=stamp(r)
        if bounds is not None and (t is None or not bounds[0]<=t<=bounds[1]):
            continue
        grouped[int(r['message_id'])].append(r)
    result=[]
    for mid,rows in sorted(grouped.items()):
        times=[t for r in rows if (t:=stamp(r)) is not None]
        delta=[round(b-a,6) for a,b in zip(times,times[1:])]
        positive=[d for d in delta if d>0]
        step=median(positive) if positive and mid in PERIODIC else None
        count=empty=0
        if mid in (138,139):
            for r in rows:
                preview=bytes.fromhex(r.get('payload_preview_hex',''))
                if len(preview)>=4:
                    n=struct.unpack_from('<I',preview)[0];count+=n;empty+=n==0
        result.append(dict(id=mid,name=NAMES.get(mid,rows[0].get('message_name',str(mid))),count=len(rows),
                           timed=len(times),invalid_time=len(rows)-len(times),hz=1/step if step else None,
                           max_gap=max(positive) if positive else None,
                           missing=sum(max(0,round(d/step)-1) for d in positive) if step else None,
                           duplicates=sum(d==0 for d in delta),backwards=sum(d<0 for d in delta),
                           observations=count if mid in (138,139) else None,empty=empty if mid in (138,139) else None))
    return result

def signal_details(folder,bounds=None):
    from converting.to_rinex.rinex305_toolkit.rinex305_toolkit.rinex305_conversion_full import parse_rangecmp_record,SIGNAL_MAP_STANDARD
    bins=sorted(set((folder/'original').glob('*.BIN'))|set((folder/'original').glob('*.bin')))
    if len(bins)!=1:
        raise ValueError('Detalizētam novērojumu pārskatam vajadzīgs viens oriģinālais BIN fails.')
    grouped={};skipped=malformed=records=0
    epochs=defaultdict(list)
    with bins[0].open('rb') as f:
        for row in read_index(folder):
            mid=int(row['message_id']);t=stamp(row)
            if mid not in (138,139) or (bounds is not None and (t is None or not bounds[0]<=t<=bounds[1])):
                continue
            f.seek(int(row['file_offset'])+24)
            payload=f.read(int(row['message_len']))
            if len(payload)<4:
                malformed+=1;continue
            count=struct.unpack_from('<I',payload)[0]
            if len(payload)<4+24*count:
                malformed+=1;continue
            sats=set();code_sats=set();phase_sats=set()
            epoch=dict(t=t,observations=count,decoded=0,code=0,phase=0,doppler=0,cn0_sum=0,cn0_count=0)
            for i in range(count):
                records+=1
                parsed=parse_rangecmp_record(payload[4+i*24:28+i*24],SIGNAL_MAP_STANDARD)
                if parsed is None:
                    skipped+=1;continue
                sat,signal,obs,_,_=parsed
                sats.add(sat);epoch['decoded']+=1
                key=(mid,sat,signal)
                if key not in grouped:
                    grouped[key]=dict(antenna=NAMES[mid],satellite=sat,signal=signal,count=0,code=0,phase=0,doppler=0,cn0=Counter())
                r=grouped[key];r['count']+=1
                for label,attribute in [('code','psr'),('phase','adr'),('doppler','doppler')]:
                    value=getattr(obs,attribute)
                    r[label]+=value is not None and math.isfinite(value)
                    epoch[label]+=value is not None and math.isfinite(value)
                if obs.psr is not None and math.isfinite(obs.psr):
                    code_sats.add(sat)
                if obs.adr is not None and math.isfinite(obs.adr):
                    phase_sats.add(sat)
                if obs.cn0 is not None and math.isfinite(obs.cn0):
                    r['cn0'][obs.cn0]+=1
                    epoch['cn0_sum']+=obs.cn0;epoch['cn0_count']+=1
            if t is not None:
                epoch.update(satellites=len(sats),code_satellites=len(code_sats),phase_satellites=len(phase_sats))
                epochs[mid].append(epoch)
    result=[]
    for key,r in sorted(grouped.items()):
        hist=r.pop('cn0');n=sum(hist.values())
        r.update(cn0_mean=sum(k*v for k,v in hist.items())/n if n else None,cn0_min=min(hist) if n else None,cn0_max=max(hist) if n else None)
        result.append(r)
    quality={}
    for mid,items in epochs.items():
        start=bounds[0] if bounds else min(e['t'] for e in items)
        end=bounds[1] if bounds else max(e['t'] for e in items)
        width=max(1,math.ceil((end-start)/600));buckets=defaultdict(list)
        for e in items:
            buckets[int((e['t']-start)//width)].append(e)
        chart=[]
        for i in range(int((end-start)//width)+1):
            batch=buckets.get(i,[]);n=len(batch)
            total=sum(e['decoded'] for e in batch);cn=sum(e['cn0_count'] for e in batch)
            row=dict(t=start+i*width,count=n,
                     cn0=sum(e['cn0_sum'] for e in batch)/cn if cn else None,
                     code_pct=100*sum(e['code'] for e in batch)/total if total else None,
                     phase_pct=100*sum(e['phase'] for e in batch)/total if total else None,
                     doppler_pct=100*sum(e['doppler'] for e in batch)/total if total else None)
            for field in ('satellites','code_satellites','phase_satellites','observations'):
                row[field]=sum(e[field] for e in batch)/n if n else None
            chart.append(row)
        quality[str(mid)]=dict(chart=chart,bin_seconds=width,epochs=len(items),
                               empty=sum(e['observations']==0 for e in items),
                               fewer_than_four_code_satellites=sum(e['code_satellites']<4 for e in items),
                               satellite_median=median(e['satellites'] for e in items),
                               code_satellite_median=median(e['code_satellites'] for e in items),
                               phase_satellite_median=median(e['phase_satellites'] for e in items))
    return dict(signals=result,records=records,unsupported=skipped,malformed=malformed,quality=quality)
