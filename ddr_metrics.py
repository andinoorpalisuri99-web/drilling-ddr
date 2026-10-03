"""Derived production and commercial measures. Never rewrite raw DDR history.

Use unrounded depth/recovered values and Decimal for the contractual 95% boundary.
All dashboard, commercial and export consumers use this module.
"""
import json
import re
from decimal import Decimal, InvalidOperation
from ddr_detail import ACTIVITIES

ZERO = Decimal('0')
HOUR_LABELS = {
    'drilling': 'Pengeboran OH / coring',
    'support': 'Aktivitas pendukung',
    'moving': 'Mobilisasi / travelling',
    'standby': 'Menunggu / cuaca / standby',
    'routine': 'P2H / briefing / istirahat',
    'maintenance': 'Breakdown / repair / maintenance',
    'unverified': 'Waktu perlu verifikasi',
}

def dec(value):
    if value in ('', None): raise ValueError('Nilai belum diisi')
    try: value = Decimal(str(value))
    except InvalidOperation: raise ValueError('Nilai bukan angka')
    if not value.is_finite() or value < 0: raise ValueError('Nilai tidak valid')
    return value

def detail(row):
    value=row.get('ddr_detail')
    return json.loads(value) if isinstance(value,str) and value else (value or {})

def hour_group(name):
    if name in ACTIVITIES['Drilling']: return 'drilling'
    if name in ('Repair & Maintenance','Breakdown','Maintenance'): return 'maintenance'
    if name in ACTIVITIES['Moving'] or name=='Travelling': return 'moving'
    if name in ('Pre Start Check (P2H)','Briefing (P5M)','Rest Time','Safety Meeting'): return 'routine'
    if name in ACTIVITIES['Activity'] or name=='Geophysical Logging': return 'support'
    if name in ACTIVITIES['Standby Activity']: return 'standby'
    return 'unverified'

def clock(value):
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',str(value or '')): raise ValueError('Jam tidak valid')
    return int(value[:2])*60+int(value[3:])

def activity_minutes(item):
    return (clock(item['to'])-clock(item['from']))%1440 or 1440

def hours(row):
    result={k:0 for k in HOUR_LABELS};issues=[]
    activities=detail(row).get('activities',[])
    for item in activities:
        try: result[hour_group(item.get('name'))]+=activity_minutes(item)
        except (ValueError,KeyError): issues.append('Jam aktivitas tidak lengkap')
    if not activities:
        # Neither an aggregate nor a shift duration proves mechanical downtime.
        result['unverified']=int(row.get('downtime_min') or 0)
        if row.get('start_time') and row.get('end_time'):
            result['unverified']=(clock(row['end_time'])-clock(row['start_time']))%1440 or 1440
        issues.append('DDR belum memiliki rincian aktivitas waktu')
    return result,issues

def run_measure(item):
    length=dec(item.get('to'))-dec(item.get('from'))
    recovered=dec(item.get('recovered'))
    if length<=0 or recovered>length: raise ValueError('Interval/recovered tidak valid')
    return length,recovered,('Coring' if recovered*100>=length*95 else 'Open Hole')

def meterage(row):
    d=detail(row);issues=[];actual=dec(row['end_depth'])-dec(row['start_depth'])
    oh=core=low=high=unknown=ZERO;intervals=[];run_rows=[]
    for n,item in enumerate(d.get('open_holes',[]),1):
        try:
            a,b=dec(item.get('from')),dec(item.get('to'))
            if b<=a:raise ValueError('Interval tidak valid')
            oh+=b-a;intervals.append((a,b))
        except ValueError:issues.append(f'Interval OH baris {n} belum valid')
    for n,item in enumerate(d.get('runs',[]),1):
        try:
            a,b=dec(item.get('from')),dec(item.get('to'))
            if b<=a:raise ValueError('Interval tidak valid')
            length=b-a;core+=length;intervals.append((a,b))
        except ValueError:
            issues.append(f'Core run {n}: interval belum valid');continue
        try:
            _,recovered,category=run_measure(item)
            if category=='Coring':high+=length
            else:low+=length
            pct=float(recovered/length*100)
        except ValueError:
            unknown+=length;category='Perlu verifikasi';pct=None
            issues.append(f'Core run {n}: recovered belum valid')
        run_rows.append({'run':item.get('run') or str(n),'from':float(a),'to':float(b),'cored_m':float(length),'recovery_pct':pct,'tariff_category':category})
    cursor=dec(row['start_depth'])
    for a,b in sorted(intervals):
        if abs(a-cursor)>Decimal('0.000001'):issues.append('Interval OH/coring memiliki gap atau overlap');break
        cursor=b
    if abs(cursor-dec(row['end_depth']))>Decimal('0.000001') or abs(oh+core-actual)>Decimal('0.000001'):
        issues.append('Total interval OH/coring belum sama dengan meter aktual')
    if actual<0:issues.append('Kedalaman akhir kurang dari awal')
    red=d.get('redrill',{})
    is_redrill=red.get('kind')=='Redrill'
    if not is_redrill and red.get('parent') not in (None,'','-') and re.search(r'R\d*$',str(row.get('hole_code','')),re.I):
        issues.append('ID/parent mengarah ke redrill tetapi jenis masih Normal; admin perlu verifikasi')
    return {'actual_m':float(actual),'actual_oh_m':float(oh),'actual_core_m':float(core),
            'low_recovery_m':float(low),'tariff_oh_m':float(oh+low),'tariff_core_m':float(high),
            'unclassified_core_m':float(unknown),'unclassified_m':float(max(ZERO,actual-oh-low-high)),
            'is_redrill':is_redrill,'runs':run_rows,'issues':list(dict.fromkeys(issues)),
            'classification_complete':unknown==0 and not any('interval' in s.lower() or 'kedalaman' in s.lower() for s in issues)}

def commercial(row):
    m=meterage(row);d=detail(row)
    prices=row.get('pricing_snapshot');prices=json.loads(prices or 'null') if isinstance(prices,str) else prices
    rates=(prices or {}).get('prices',{});missing=[k for k,v in d.get('consumables',{}).items() if v and k not in rates]
    known=sum(dec(v)*dec(rates.get(k,0)) for k,v in d.get('consumables',{}).items())
    tariff_missing=[key for key,meters in [('Open Hole',m['tariff_oh_m']),('Core Hole',m['tariff_core_m'])] if meters and key not in rates]
    price_ready=bool(prices) and not tariff_missing and m['classification_complete']
    gross=float(dec(m['tariff_oh_m'])*dec(rates.get('Open Hole',0))+dec(m['tariff_core_m'])*dec(rates.get('Core Hole',0))) if price_ready else None
    eligible=row.get('billing_status')=='Billable' and row.get('status')!='Rejected'
    approved=eligible and row.get('status')=='Approved'
    return {**m,'id':row['id'],'rig_id':row['rig_id'],'rig':row.get('rig',row.get('rig_code_snapshot','')),
            'hole':row.get('hole_code',''),'date':row['work_date'],'status':row['status'],
            'billing':row.get('billing_status','Pending'),'billing_note':row.get('billing_note',''),
            'revision':row.get('revision',0),'redrill':d.get('redrill',{}),
            'open_hole_m':m['tariff_oh_m'],'core_m':m['tariff_core_m'],
            'eligible_m':m['actual_m'] if eligible else 0,
            'nonbillable_m':m['actual_m'] if row.get('billing_status')=='Non-billable' and row['status']!='Rejected' else 0,
            'pending_m':m['actual_m'] if row.get('billing_status')=='Pending' and row['status']!='Rejected' else 0,
            'potential_value':gross,'billable_value':gross if approved else 0,
            'unbilled_value':gross if row.get('billing_status')=='Non-billable' else 0,
            'known_material_cost':float(known),'missing_prices':missing,'missing_tariffs':tariff_missing,
            'pricing':prices,'price_ready':price_ready}

METRIC_KEYS=('actual_m','actual_oh_m','actual_core_m','tariff_oh_m','tariff_core_m','low_recovery_m','unclassified_m','eligible_m','paid_normal_m','paid_redrill_m','nonbillable_m','pending_m','approved_billable_m')

def overview(rows):
    totals={k:ZERO for k in METRIC_KEYS};by_rig={};by_day={};times={k:0 for k in HOUR_LABELS};issues=[]
    for r in rows:
        if r['status']=='Rejected' or not r.get('rig_active',1):continue
        m=meterage(r);h,hi=hours(r)
        for k,v in h.items():times[k]+=v
        if m['issues'] or hi:issues.append({'id':r['id'],'issues':m['issues']+hi})
        values={k:ZERO for k in METRIC_KEYS}
        for k in ('actual_m','actual_oh_m','actual_core_m','tariff_oh_m','tariff_core_m','low_recovery_m','unclassified_m'):values[k]=dec(m[k])
        if r.get('billing_status')=='Billable':
            values['eligible_m']=dec(m['actual_m']);values['paid_redrill_m' if m['is_redrill'] else 'paid_normal_m']=values['eligible_m']
            if r['status']=='Approved':values['approved_billable_m']=values['eligible_m']
        elif r.get('billing_status')=='Non-billable':values['nonbillable_m']=dec(m['actual_m'])
        else:values['pending_m']=dec(m['actual_m'])
        rig=str(r['rig_id']);label=r.get('rig',r.get('rig_code_snapshot')) or f'Rig #{rig}'
        bucket=by_rig.setdefault(rig,{'rig_id':r['rig_id'],'label':label,**{k:ZERO for k in METRIC_KEYS}})
        day=by_day.setdefault(r['work_date'],{'label':r['work_date'],**{k:ZERO for k in METRIC_KEYS}})
        for k,v in values.items():totals[k]+=v;bucket[k]+=v;day[k]+=v
    def numeric(data):return {k:float(v) if isinstance(v,Decimal) else v for k,v in data.items()}
    return {'metrics':numeric(totals),'by_rig':[numeric(v) for v in by_rig.values()],
            'by_day':[numeric(by_day[k]) for k in sorted(by_day)],'time_minutes':times,
            'hours':{k:v/60 for k,v in times.items()},'verification':issues,'hour_labels':HOUR_LABELS}
