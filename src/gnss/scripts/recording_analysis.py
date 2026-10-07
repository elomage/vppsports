"""Read-only acquisition metrics from receiver CSV and RINEX 3 observations."""
from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from threading import RLock
from observation_analysis import stream_summary

ROOT = Path(__file__).resolve().parents[1]
_cache = {}
_lock = RLock()


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def timestamp(value):
    try:
        t = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.timestamp() if 2000 <= t.year <= datetime.now(timezone.utc).year + 1 else None
    except (ValueError, TypeError):
        return None


def stats(values):
    a = sorted(v for v in values if v is not None and math.isfinite(v))
    if not a:
        return dict(n=0, mean=None, median=None, p95=None, min=None, max=None)
    i = (len(a) - 1) * .95
    lo = int(i)
    p95 = a[lo] + (a[min(lo + 1, len(a) - 1)] - a[lo]) * (i - lo)
    return dict(n=len(a), mean=sum(a)/len(a), median=median(a), p95=p95, min=a[0], max=a[-1])


def norm(row, fields):
    a = [number(row.get(k)) for k in fields]
    return math.sqrt(sum(v*v for v in a)) if all(v is not None for v in a) else None


def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def position_track(path, bounds=None):
    """Read RTKLIB WGS84 LLH output; timestamps in these recordings use GPST/UTC."""
    points=[]; supported=False; offset=0; segment=0; previous=None
    if not path.exists():
        return points
    with path.open(errors='replace') as f:
        for line in f:
            if line.startswith('%'):
                if 'latitude(deg)' in line and ('GPST' in line or 'UTC' in line):
                    supported=True; offset=18 if 'GPST' in line else 0
                continue
            if not supported or not line.strip():
                continue
            a=line.split()
            try:
                if '/' in a[0]:
                    t=datetime.fromisoformat(a[0].replace('/','-')+'T'+a[1]).replace(tzinfo=timezone.utc).timestamp()-offset
                else:
                    t=datetime(1980,1,6,tzinfo=timezone.utc).timestamp()+int(a[0])*604800+float(a[1])-offset
                lat,lon,height=map(float,a[2:5]); quality=int(a[5])
                if quality<=0 or not all(math.isfinite(v) for v in (t,lat,lon,height)) or not -90<=lat<=90 or not -180<=lon<=180:
                    segment+=1; previous=None; continue
                if previous is not None and (t<=previous or t-previous>1):
                    segment+=1
                points.append(dict(t=t,lat=lat,lon=lon,height=height,quality=quality,segment=segment,
                                   selected=bounds is None or bounds[0]<=t<=bounds[1]))
                previous=t
            except (ValueError,IndexError,OverflowError):
                segment+=1; previous=None
    return points


def map_tracks(folder, bounds=None):
    return {name:position_track(folder/'ppk'/filename,bounds) for name,filename in (
        ('single','observation_single.pos'),('ppk','solution.pos'),
        ('float','solution_float.pos'),('dgps','solution_dgps.pos'))}


def observation_position(folder,bounds=None):
    """RTKLIB LLH solution uncertainty, with GPST explicitly converted to UTC."""
    path=folder/'ppk/observation_single.pos'
    report=next(iter((folder/'rinex').glob('*conversion_report.txt')),None)
    if not path.exists():
        return dict(chart=[],count=0,source='Nav observation_single.pos',main=False)
    main=bool(report and 'OBS source: obsvmcmpb' in report.read_text(errors='replace'))
    points=[];supported=False
    with path.open() as f:
        for line in f:
            if line.startswith('%'):
                if 'GPST' in line and 'latitude(deg)' in line and 'sdn(m)' in line:
                    supported=True
                continue
            if not supported or not line.strip():
                continue
            a=line.split()
            try:
                t=datetime(1980,1,6,tzinfo=timezone.utc).timestamp()+int(a[0])*604800+float(a[1])-18
                if bounds is not None and not bounds[0]<=t<=bounds[1]:
                    continue
                sd=[float(v) for v in a[7:10]]
                height=float(a[4]);quality=int(a[5])
                if quality<=0 or len(sd)!=3 or not all(math.isfinite(v) and v>=0 for v in sd) or not math.isfinite(height):
                    continue
                points.append(dict(t=t,sigma=math.sqrt(sum(v*v for v in sd)),height=height))
            except (ValueError,IndexError):
                continue
    if not points:
        return dict(chart=[],count=0,source=str(path.relative_to(folder)),main=main)
    width=max(1,math.ceil((points[-1]['t']-points[0]['t'])/600));buckets=defaultdict(list)
    for p in points:
        buckets[int((p['t']-points[0]['t'])//width)].append(p)
    chart=[]
    for i in range(max(buckets)+1):
        rows=buckets.get(i,[])
        chart.append(dict(t=points[0]['t']+i*width,count=len(rows),sigma=stats([r['sigma'] for r in rows])['mean'],height=stats([r['height'] for r in rows])['mean']))
    return dict(chart=chart,count=len(points),source=str(path.relative_to(folder)),main=main,bin_seconds=width,
                sigma=stats([p['sigma'] for p in points]))


def list_sessions():
    return [dict(id=p.name, date=p.name[:8], has_csv=(p/'csv/bestnavxyz.csv').exists(),
                 bytes=sum(f.stat().st_size for f in (p/'original').glob('*') if f.is_file()))
            for p in sorted((ROOT/'out').iterdir(), reverse=True) if p.is_dir()]


def get_session(name):
    base = (ROOT/'out').resolve()
    p = (base/name).resolve()
    if p.parent != base or not p.is_dir():
        raise ValueError('Nezināms ieraksts')
    return p


def rinex_metrics(path, bounds=None):
    """S observables only; do not confuse the one-digit SSI flag with C/N0."""
    types = defaultdict(list)
    signals = defaultdict(list)
    epochs = []
    lli = 0
    phase = 0
    sat_rows = 0
    active = bounds is None
    time_system = 'GPS'
    with path.open(encoding='ascii', errors='replace') as f:
        system = None
        for line in f:
            if 'TIME OF FIRST OBS' in line:
                time_system = line[48:51].strip() or 'GPS'
            if 'SYS / # / OBS TYPES' in line:
                system = line[0] if line[0].strip() else system
                types[system].extend(line[7:60].split())
            if 'END OF HEADER' in line:
                break
        for line in f:
            if line.startswith('>'):
                active = False
                parts = line.split()
                if len(parts) >= 9 and parts[7] in ('0', '1'):
                    try:
                        t = datetime(*map(int, parts[1:6]), tzinfo=timezone.utc).timestamp()+float(parts[6])
                        utc = t - (18 if time_system == 'GPS' else 0)
                        if bounds and time_system not in ('GPS', 'UTC'):
                            raise ValueError('Laika filtram neatbalstīta RINEX laika sistēma: '+time_system)
                        active = bounds is None or bounds[0] <= utc <= bounds[1]
                        if active:
                            epochs.append(t)
                    except ValueError:
                        pass
                continue
            if not active:
                continue
            if len(line) < 3 or line[0] not in types or not line[1:3].isdigit():
                continue
            sat_rows += 1
            for i, obs in enumerate(types[line[0]]):
                field = line[3+16*i:3+16*(i+1)]
                n = number(field[:14])
                if obs.startswith('S') and n is not None and n > 0:
                    signals[line[0] + ' · ' + obs].append(n)
                if obs.startswith('L') and n is not None:
                    phase += 1
                    if len(field) > 14 and field[14].isdigit() and int(field[14]) & 1:
                        lli += 1
    diffs = [b-a for a,b in zip(epochs, epochs[1:]) if b>a]
    step = median(diffs) if diffs else None
    values = [v for a in signals.values() for v in a]
    return dict(file=path.name, epochs=len(epochs), satellite_rows=sat_rows,
                hz=1/step if step else None, gaps=sum(d>step*1.5 for d in diffs) if step else 0,
                cn0=stats(values), signals={k:stats(v) for k,v in sorted(signals.items())},
                phase_observations=phase, loss_of_lock_flags=lli,
                histogram=[dict(label=f'{a}–{a+5}', count=sum(a<=v<a+5 for v in values)) for a in range(0,65,5)])


def analyze(name, include_signal=True, start_s=None, end_s=None):
    p = get_session(name)
    files = [f for folder in ('csv','original','rinex','ppk','imu') for f in (p/folder).glob('*') if f.is_file()]
    signature = tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in sorted(files))
    for value in (start_s, end_s):
        if value is not None and (number(value) is None or float(value)<0):
            raise ValueError('Laika robežām jābūt nenegatīvām sekundēm.')
    start_s = float(start_s) if start_s is not None else None
    end_s = float(end_s) if end_s is not None else None
    if start_s is not None and end_s is not None and start_s>end_s:
        raise ValueError('Sākums nedrīkst būt pēc beigām.')
    key = (name, include_signal, start_s, end_s)
    with _lock:
        if key in _cache and _cache[key][0] == signature:
            return _cache[key][1]
    rows = read_csv(p/'csv/bestnavxyz.csv')
    source = 'csv/bestnavxyz.csv'
    if not rows and not (p/source).exists():
        # Include unprocessed/failed acquisitions without modifying their files.
        from converting.to_csv.unicore_n4_extract import iter_n4_frames, decode_bestnavxyz
        bins = sorted(set((p/'original').glob('*.BIN')) | set((p/'original').glob('*.bin')))
        if bins and sum(f.stat().st_size for f in bins) <= 2_000_000:
            rows = [decode_bestnavxyz(f) for b in bins for f in iter_n4_frames(b.read_bytes()) if f['message_id']==240]
            rows = [r for r in rows if r]
            source = 'original/*.BIN (nolasīts atmiņā)'
    full_times = [t for r in rows if (t := timestamp(r.get('utc'))) is not None]
    full_start = min(full_times) if full_times else None
    full_end = max(full_times) if full_times else None
    bounds = None
    if start_s is not None or end_s is not None:
        if full_start is None:
            raise ValueError('Ierakstam nav derīga laika.')
        bounds = (full_start+(start_s or 0), min(full_end,full_start+end_s) if end_s is not None else full_end)
        if bounds[0]>full_end:
            raise ValueError('Sākums ir ārpus ieraksta.')
    def in_range(row):
        if bounds is None:
            return True
        t = timestamp(row.get('utc', row.get('time')))
        return t is not None and bounds[0]<=t<=bounds[1]
    # Local east/north projection with a common origin for the entire ride.
    track=[]; origin=None; previous=None; segment=0
    for row in rows:
        t=timestamp(row.get('utc')); radius=norm(row,('x_m','y_m','z_m'))
        if t is None or row.get('position_solution_status')!='SOL_COMPUTED' or radius is None or not 6e6<radius<7e6:
            previous=None; segment+=1; continue
        xyz=[number(row[k]) for k in ('x_m','y_m','z_m')]
        if origin is None:
            origin=xyz
            lon=math.atan2(xyz[1],xyz[0]); lat=math.atan2(xyz[2],math.hypot(*xyz[:2]))
        if previous is not None and (t-previous>1 or t<=previous):
            segment+=1
        dx,dy,dz=[v-o for v,o in zip(xyz,origin)]
        horizontal=math.hypot(xyz[0],xyz[1])
        latitude=math.atan2(xyz[2],horizontal*(1-0.00669437999014))
        for _ in range(6):
            curvature=6378137/math.sqrt(1-0.00669437999014*math.sin(latitude)**2)
            latitude=math.atan2(xyz[2]+0.00669437999014*curvature*math.sin(latitude),horizontal)
        # Projection onto the ellipsoid normal is stable at the poles too.
        height=horizontal*math.cos(latitude)+xyz[2]*math.sin(latitude)-6378137*math.sqrt(1-0.00669437999014*math.sin(latitude)**2)
        track.append(dict(t=t,e=-math.sin(lon)*dx+math.cos(lon)*dy,
                          height=height,
                          lat=math.degrees(latitude),lon=math.degrees(math.atan2(xyz[1],xyz[0])),
                          n=-math.sin(lat)*math.cos(lon)*dx-math.sin(lat)*math.sin(lon)*dy+math.cos(lat)*dz,
                          segment=segment,selected=bounds is None or bounds[0]<=t<=bounds[1]))
        previous=t
    rows=[r for r in rows if in_range(r)]
    timed=[]; valid=[]; series=[]; invalid_time=0
    statuses=Counter(); position_types=Counter(); speeds=[]; sigmas=[]; sat_used=[]; sat_tracked=[]
    zero_coordinates=0; computed_zero_sat=0; qualified=0
    for row in rows:
        t = timestamp(row.get('utc'))
        xyz = norm(row, ('x_m','y_m','z_m'))
        status = str(row.get('position_solution_status','nav'))
        statuses[status]+=1
        position_types[str(row.get('position_type','nav'))]+=1
        zero_coordinates += xyz == 0
        if t is None:
            invalid_time+=1
            continue
        timed.append(t)
        ok = status=='SOL_COMPUTED' and xyz is not None and 6e6<xyz<7e6
        used=number(row.get('satellites_used')); tracked=number(row.get('satellites_tracked'))
        sat_used.append(used); sat_tracked.append(tracked)
        sigma = norm(row, ('x_sigma_m','y_sigma_m','z_sigma_m')) if ok else None
        if sigma == 0:
            sigma = None
        speed = norm(row, ('vx_mps','vy_mps','vz_mps')) if ok and row.get('velocity_solution_status')=='SOL_COMPUTED' else None
        if speed is not None:
            speed *= 3.6
            speeds.append(speed)
        if ok:
            valid.append(t); sigmas.append(sigma)
            computed_zero_sat += used == 0
            qualified += used is not None and used>=4
        series.append(dict(t=t, valid=int(ok), used=used, tracked=tracked, sigma=sigma, speed=speed))
    ordered=sorted(set(timed)); deltas=[b-a for a,b in zip(timed,timed[1:])]
    positive=[d for d in deltas if d>0]
    step=median(positive) if positive else None
    duration=ordered[-1]-ordered[0] if ordered else 0
    gaps=[dict(start=a,end=b,seconds=b-a,missing=max(0,round((b-a)/step)-1)) for a,b in zip(ordered,ordered[1:]) if step and b-a>step*1.5]
    expected=round(duration/step)+1 if step else None
    # Missing-solution runs include startup and final loss, separate from absent messages.
    outages=[]; start=None
    for item in sorted(series,key=lambda x:x['t']):
        if not item['valid'] and start is None:
            start=item['t']
        if item['valid'] and start is not None:
            outages.append(dict(start=start,end=item['t'],seconds=item['t']-start)); start=None
    if start is not None:
        end=ordered[-1]+(step or 0)
        outages.append(dict(start=start,end=end,seconds=end-start))
    headings=[r for r in read_csv(p/'csv/uniheading.csv') if in_range(r)]
    good_h=[r for r in headings if timestamp(r.get('utc')) is not None and r.get('solution_status')=='SOL_COMPUTED']
    filtered=read_csv(p/'csv/location_heading_xyz_filtered.csv')
    if not filtered:
        filtered=read_csv(p/'csv/bestnavxyz_filtered.csv')
    filtered=[r for r in filtered if in_range(r)]
    bad_filtered=sum(r.get('position_solution_status')!='SOL_COMPUTED' for r in filtered)
    obs=next(iter(sorted(f for f in (p/'rinex').glob('*') if f.suffix.lower().endswith('o') or f.suffix.lower()=='.obs')),None)
    signal=rinex_metrics(obs,bounds) if obs and include_signal else None
    # Aggregate chart bins, retaining every record in statistics and valid fraction.
    width=max(1,math.ceil(duration/600))
    buckets=defaultdict(list)
    for item in series:
        buckets[int((item['t']-ordered[0])//width)].append(item)
    chart=[]
    for i in range(int(duration//width)+1 if ordered else 0):
        items=buckets.get(i,[])
        r=dict(t=ordered[0]+i*width, count=len(items),valid=sum(x['valid'] for x in items)/len(items) if items else None)
        for k in ('used','tracked','sigma','speed'):
            r[k]=stats([x[k] for x in items])['mean']
        chart.append(r)
    products={}
    for filename in ('solution.csv','solution_float.csv','solution_dgps.csv','observation_single.csv'):
        f=p/'ppk'/filename
        if f.exists():
            with f.open(encoding='utf-8-sig',newline='') as stream:
                products[filename]=sum(1 for r in csv.DictReader(stream) if in_range(r))
    result=dict(id=name, source=source,position_tracks=map_tracks(p,bounds),observation_position=observation_position(p,bounds),streams=stream_summary(p,bounds),full_start=full_start,full_end=full_end,bounds=bounds,track=track,
                rows=len(rows), timed_rows=len(timed), invalid_time=invalid_time,
                valid=len(valid), qualified=qualified, valid_percent=100*len(valid)/len(timed) if timed else None,
                start=ordered[0] if ordered else None,end=ordered[-1] if ordered else None,duration=duration,
                hz=1/step if step else None, step=step, interval=stats(positive), expected=expected,
                missing=max(0,expected-len(ordered)) if expected else None, duplicates=len(timed)-len(ordered),
                backwards=sum(d<0 for d in deltas),gaps=gaps, outages=outages, zero_coordinates=zero_coordinates,
                computed_zero_sat=computed_zero_sat, statuses=dict(statuses),position_types=dict(position_types),
                speed=stats(speeds), sigma=stats(sigmas),sat_used=stats(sat_used),sat_tracked=stats(sat_tracked),
                heading=dict(rows=len(headings),valid=len(good_h), fixed=sum(r.get('position_type')=='NARROW_INT' for r in good_h),
                             sd=stats([number(r.get('heading_stddev_deg')) for r in good_h])),
                filtered_rows=len(filtered),bad_filtered=bad_filtered,signal=signal,chart=chart,bin_seconds=width,
                products=products,files=[dict(name=str(f.relative_to(p)).replace('\\','/'),bytes=f.stat().st_size) for f in files])
    with _lock:
        if len(_cache)>=32:
            _cache.pop(next(iter(_cache)))
        _cache[key]=(signature,result)
    return result
