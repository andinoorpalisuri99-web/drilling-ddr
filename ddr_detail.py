"""Validate and summarize the operational sections of the MMS DDR template."""
import math
import re
from datetime import datetime

ACTIVITIES = {
    'Drilling': ['Open Hole','Core Hole'],
    'Moving': ['Rig Set Down','Moving / Shifting','Rig Set Up','Setting Water Line','Make Manual Access'],
    'Activity': ['Pull Down Rods','Pull Up Rods','Condition Hole','Flushing Hole','Reaming','Install Casing','Install Instrument Geotech','Piezometer (PZ)','Vibrating Wire (VW)','Inclinometer','Stuck Rods','Freeing Rods','Repair Drillsite / Drain MudPit','Contamination handling'],
    'Standby Activity': ['Waiting Information','Prepare Drillpad & Mud pit','Waiting Logging','Blasting Evacuation','Geophysical Logging','Standby Rain','Waiting Water','Waiting Equipment','Safety Meeting','Bad Weather','Unsafe Condition','Broken Access','Rest Time','Others'],
    'Standby Repair & Maintenance': ['Repair & Maintenance','Breakdown','Maintenance','Pre Start Check (P2H)','Briefing (P5M)','Travelling'],
}
CONSUMABLES = {'HiVis':'kg','Polymer':'L','Bentonit':'sack','Aus Trol':'kg','Aus Plug':'L','Foam':'L','PVC':'m','Diesel':'L','Hydraulic':'L'}

class Invalid(ValueError):
    def __init__(self,message,field='form'):
        super().__init__(message);self.field=field;self.code='field_validation'

def group(name):
    from ddr_metrics import hour_group
    return hour_group(name)

def number(value, name, upper=None):
    try: val=float(value)
    except (TypeError, ValueError): raise ValueError(f'{name} harus berupa angka')
    if not math.isfinite(val) or val < 0 or (upper is not None and val > upper): raise ValueError(f'{name} di luar rentang')
    return val

def label(value,name,limit=150):
    val=str(value or '').strip()
    if len(val)>limit:raise ValueError(f'{name} terlalu panjang')
    return val

def time(value):
    val=str(value or '')
    if len(val)!=5 or datetime.strptime(val,'%H:%M').strftime('%H:%M')!=val:raise ValueError('Jam aktivitas tidak valid')
    return val

def parse(raw, start_depth, end_depth, start_time, end_time):
    if not isinstance(raw,dict):raise ValueError('Detail DDR tidak valid')
    if not isinstance(raw.get('identity',{}),dict) or not isinstance(raw.get('movement',{}),dict):raise ValueError('Identitas DDR tidak valid')
    identity={k:label(raw.get('identity',{}).get(k),k,120) for k in ('hole','geologist','assistant_geologist','driller','crew','azimuth','dip')}
    identity['wellsite_prepared']=raw.get('identity',{}).get('wellsite_prepared') is True
    if not identity['hole']:raise ValueError('Drillhole No. wajib diisi')
    activities=raw.get('activities',[]);runs=raw.get('runs',[]);intervals=raw.get('open_holes',[]);tools=raw.get('lost_tools',[])
    if any(not isinstance(v,list) or len(v)>80 for v in (activities,runs,intervals,tools)):raise ValueError('Jumlah baris DDR tidak valid')
    allowed={name:group for group,names in ACTIVITIES.items() for name in names}
    from ddr_metrics import HOUR_LABELS
    cleaned=[];total=0;nonproductive=0;slots=[];totals={k:0 for k in HOUR_LABELS}
    for index,item in enumerate(activities):
        if not isinstance(item,dict) or item.get('name') not in allowed:raise ValueError('Kategori aktivitas tidak valid')
        a,b=time(item.get('from')),time(item.get('to'))
        begin=int(a[:2])*60+int(a[3:]);finish=int(b[:2])*60+int(b[3:]);finish+=1440 if finish<=begin else 0
        if finish-begin>1440:raise ValueError('Durasi aktivitas tidak valid')
        slots.append((begin,finish));duration=finish-begin;total+=duration
        totals[group(item['name'])]+=duration
        if group(item['name'])!='drilling':nonproductive+=duration
        cleaned.append({'name':item['name'],'from':a,'to':b,'hours':round(duration/60,2),'note':label(item.get('note'),'Catatan aktivitas',250)})
    if slots:
        shift_begin=int(start_time[:2])*60+int(start_time[3:]);shift_end=int(end_time[:2])*60+int(end_time[3:]);shift_end+=1440 if shift_end<=shift_begin else 0
        normalized=[]
        for a,b in slots:
            if a<shift_begin:a+=1440;b+=1440
            if a<shift_begin or b>shift_end:raise ValueError('Waktu aktivitas harus berada dalam rentang shift')
            normalized.append((a,b))
        normalized.sort()
        if any(normalized[i][0]<normalized[i-1][1] for i in range(1,len(normalized))):raise Invalid('Aktivitas DDR ini memiliki jam bertumpang tindih; periksa From/To tiap baris.','activities')
        if total>shift_end-shift_begin:raise ValueError('Total aktivitas melebihi durasi shift')
    core=[]
    for index,item in enumerate(runs):
        if not isinstance(item,dict):raise ValueError('Core run tidak valid')
        a=number(item.get('from'),'Depth from');b=number(item.get('to'),'Depth to');recovered=number(item.get('recovered'),'Recovered')
        if b<=a:raise Invalid(f'Core run baris {index+1}: Depth To harus lebih besar dari Depth From.',f'runs.{index}.to')
        if recovered>round(b-a,6)+1e-6:raise Invalid(f'Core run baris {index+1}: Recovered {recovered:g} m melebihi Cored {b-a:g} m.',f'runs.{index}.recovered')
        if a<start_depth or b>end_depth:raise Invalid(f'Core run baris {index+1}: interval {a:g}–{b:g} m di luar Start/End depth {start_depth:g}–{end_depth:g} m.',f'runs.{index}.from')
        core.append({'run':label(item.get('run'),'Nomor run',40),'from':a,'to':b,'cored':round(b-a,2),'recovered':recovered,'recovery_pct':round(recovered/(b-a)*100,2),'core_loss':round(b-a-recovered,2),'rqd_pct':number(item['rqd_pct'],'RQD',100) if item.get('rqd_pct') not in ('',None) else None,'comment':label(item.get('comment'),'Komentar core',250)})
    core.sort(key=lambda x:x['from'])
    if any(core[i]['from']<core[i-1]['to'] for i in range(1,len(core))):raise ValueError('Core run tidak boleh tumpang tindih')
    holes=[]
    for index,item in enumerate(intervals):
        if not isinstance(item,dict):raise ValueError('Open hole tidak valid')
        a=number(item.get('from'),'Open hole from');b=number(item.get('to'),'Open hole to')
        if b<=a or a<start_depth or b>end_depth:raise Invalid(f'Open Hole baris {index+1}: Depth To harus lebih besar dari From dan interval harus berada pada {start_depth:g}–{end_depth:g} m.',f'open_holes.{index}.to')
        holes.append({'from':a,'to':b,'interval':round(b-a,2),'lithology':label(item.get('lithology'),'Lithology',120)})
    holes.sort(key=lambda x:x['from'])
    if any(holes[i]['from']<holes[i-1]['to'] for i in range(1,len(holes))):raise ValueError('Open hole tidak boleh tumpang tindih')
    if raw.get('version')==2:
        if not activities:raise Invalid('Aktivitas: tambahkan minimal satu baris waktu kegiatan DDR ini.','activities')
        combined=sorted([(x['from'],x['to']) for x in core+holes])
        cursor=start_depth
        for a,b in combined:
            if abs(a-cursor)>0.000001:
                raise ValueError(f'Interval kedalaman: {cursor:g} m ke {a:g} m memiliki '+('celah' if a>cursor else 'tumpang tindih'))
            cursor=b
        if abs(cursor-end_depth)>0.000001:raise Invalid(f'End depth {end_depth:g} m tidak cocok dengan ujung interval {cursor:g} m.','end_depth')
    redrill=raw.get('redrill',{})
    if not isinstance(redrill,dict):raise ValueError('Redrill tidak valid')
    mode=redrill.get('kind','Normal');parent=label(redrill.get('parent'),'Hole asal',120).upper()
    if mode not in ('Normal','Redrill'):raise ValueError('Jenis pekerjaan tidak valid')
    identity['hole']=identity['hole'].upper()
    if mode=='Redrill':
        if not parent or parent==identity['hole'] or not re.search(r'R[1-9][0-9]*$',identity['hole']):raise ValueError('Redrill: isi hole asal dan ID hole berakhiran R1, R2, dst.')
        if not label(redrill.get('reason'),'Alasan redrill',250):raise ValueError('Alasan redrill wajib diisi')
    readings=raw.get('readings',[])
    if not isinstance(readings,list) or len(readings)>160:raise ValueError('Pembacaan parameter tidak valid')
    units=raw.get('units',{})
    permitted={'wob':('kN','kgf','lbf'),'torque':('Nm','kNm','lbf.ft'),'pump_pressure':('bar','psi','MPa')}
    if not isinstance(units,dict):raise ValueError('Satuan parameter tidak valid')
    for k,opts in permitted.items():
        if units.get(k) not in (None,'',*opts):raise ValueError('Satuan '+k+' tidak dikenal')
    clean_readings=[]
    for x in readings:
        if not isinstance(x,dict):raise ValueError('Pembacaan parameter tidak valid')
        clock=time(x.get('at'));activity=x.get('activity')
        if activity not in ACTIVITIES['Drilling']:raise ValueError('Parameter hanya untuk Open Hole atau Core Hole')
        t=int(clock[:2])*60+int(clock[3:]);sb=int(start_time[:2])*60+int(start_time[3:]);t+=1440 if t<sb else 0
        matches=False
        for a in cleaned:
            lo=int(a['from'][:2])*60+int(a['from'][3:]);hi=int(a['to'][:2])*60+int(a['to'][3:]);hi+=1440 if hi<=lo else 0
            if lo<sb:lo+=1440;hi+=1440
            if a['name']==activity and lo<=t<hi:matches=True
        if not matches:raise ValueError('Jam pembacaan '+clock+' harus berada pada aktivitas '+activity)
        row={'at':clock,'activity':activity}
        for k in ('wob','rpm','torque','pump_pressure'):
            row[k]=number(x[k],k) if x.get(k) not in ('',None) else None
            if row[k] is not None and k!='rpm' and not units.get(k):raise ValueError('Satuan '+k+' belum dikonfirmasi admin untuk rig ini')
        if all(row[k] is None for k in ('wob','rpm','torque','pump_pressure')):raise ValueError('Isi minimal satu pembacaan parameter')
        clean_readings.append(row)
    lost=[]
    for item in tools:
        if not isinstance(item,dict):raise ValueError('Lost tool tidak valid')
        qty=number(item.get('qty'),'Jumlah lost tool')
        if qty!=int(qty):raise ValueError('Jumlah lost tool harus bilangan bulat')
        lost.append({'tool':label(item.get('tool'),'Alat hilang',120),'size':label(item.get('size'),'Ukuran',50),'qty':int(qty),'remark':label(item.get('remark'),'Keterangan',250)})
    cons=raw.get('consumables',{})
    if not isinstance(cons,dict) or any(k not in CONSUMABLES for k in cons):raise ValueError('Consumable tidak valid')
    return {'version':raw.get('version',1),'redrill':{'kind':mode,'parent':parent,'reason':label(redrill.get('reason'),'Alasan redrill',250)},'readings':clean_readings,'units':units,'identity':identity,'activities':cleaned,'runs':core,'open_holes':holes,'lost_tools':lost,
            'movement':{'distance_m':number(raw.get('movement',{}).get('distance_m') or 0,'Jarak pindah'),'from_hole':label(raw.get('movement',{}).get('from_hole'),'Dari drillhole',120),'to_hole':label(raw.get('movement',{}).get('to_hole'),'Ke drillhole',120)},
            'consumables':{key:number(cons.get(key) or 0,key) for key in CONSUMABLES},
            'summary':{'group_minutes':totals,'activity_minutes':total,'activity_hours':round(total/60,2),'non_drilling_min':nonproductive,'standby_maintenance_min':totals['standby']+totals['maintenance'],'breakdown_maintenance_min':totals['maintenance'],'cored_m':round(sum(x['cored'] for x in core),2),'recovered_m':round(sum(x['recovered'] for x in core),2),'open_hole_m':round(sum(x['interval'] for x in holes),2)}}


def validate_preparer(detail):
    """New submissions/corrections require a named preparer and explicit confirmation.

    Stored legacy reports are read without this validation; they are never
    marked confirmed merely because a name was already present.
    """
    identity=(detail or {}).get('identity',{})
    if not identity.get('geologist','').strip():
        raise Invalid('Isi nama Wellsite Geologist / Geotech yang menyusun DDR.','identity.geologist')
    if identity.get('wellsite_prepared') is not True:
        raise Invalid('Konfirmasi bahwa DDR disusun oleh Wellsite Geologist / Geotech yang tercantum.','identity.wellsite_prepared')
