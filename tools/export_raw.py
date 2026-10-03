"""Export operational tables as UTF-8 CSV files (excludes accounts/sessions)."""
import csv
import os
import sqlite3
import sys
from pathlib import Path

source=Path(os.environ.get('DRILLING_DB',Path(__file__).resolve().parent.parent/'drilling.db'))
if not source.exists():raise SystemExit('Database belum ditemukan')
destination=Path(sys.argv[1]) if len(sys.argv)>1 else source.parent/'exports'
destination.mkdir(parents=True,exist_ok=True)
tables=('rigs','rig_revisions','reports','audit','equipment','materials','stock_moves','core_boxes','samples','custody_events','programs','expenses','invoices','activity','rig_targets','target_revisions','deletion_log','period_targets','period_target_revisions','tracking_tokens','period_target_baselines','qa_revisions')
with sqlite3.connect(source) as db:
    db.row_factory=sqlite3.Row
    # Keep every CSV in one committed database snapshot while operators write DDRs.
    db.execute('BEGIN')
    for table in tables:
        cursor=db.execute(f'SELECT * FROM {table}')
        with (destination/f'{table}.csv').open('w',newline='',encoding='utf-8-sig') as file:
            writer=csv.writer(file);writer.writerow([x[0] for x in cursor.description]);writer.writerows(cursor)
    # Keep the raw archival CSV unchanged, and provide current canonical measures.
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    from ddr_metrics import commercial,hours
    derived=[]
    for record in db.execute("SELECT * FROM reports WHERE rig_id IN (SELECT id FROM rigs WHERE active=1) AND status!='Rejected'"):
        row=dict(record);m=commercial(row);h,_=hours(row)
        derived.append({k:m[k] for k in ('id','actual_m','actual_oh_m','actual_core_m','tariff_oh_m','tariff_core_m','eligible_m','nonbillable_m','pending_m','billing','status','billable_value')}|{'breakdown_maintenance_min':h['maintenance'],'verification':'; '.join(m['issues'])})
    with (destination/'reports_derived.csv').open('w',newline='',encoding='utf-8-sig') as file:
        keys=list(derived[0]) if derived else ['id']
        writer=csv.DictWriter(file,fieldnames=keys);writer.writeheader();writer.writerows(derived)
print(destination)
