"""Portable DDR downloads. Template geometry is shared by XLSX and PDF.

XLSX generation fills a pre-authored OOXML template with typed cells; no Excel
installation or spreadsheet writer dependency is needed on the application host.
"""
import copy
import io
import json
import math
import re
import threading
from functools import lru_cache
import zipfile
import xml.etree.ElementTree as E
from datetime import datetime
from pathlib import Path
from html import escape
import ddr_detail
import ddr_rules

ROOT=Path(__file__).resolve().parent
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
E.register_namespace('',NS);E.register_namespace('r',REL)
def tag(n):return '{'+NS+'}'+n
XML_LOCK=threading.RLock()
def xml(x):
    with XML_LOCK:
        namespace=x.tag.split('}')[0][1:]
        E.register_namespace('',namespace)
        return E.tostring(x,encoding='utf-8',xml_declaration=True)
def col(n):
    out=''
    while n:n,k=divmod(n-1,26);out=chr(65+k)+out
    return out

def minutes(a):return (int(a['to'][:2])*60+int(a['to'][3:])-int(a['from'][:2])*60-int(a['from'][3:]))%1440 or 1440

def activity_text(item):
    return ' - '.join(str(item.get(k) or '').strip() for k in ('name','note') if str(item.get(k) or '').strip())

def preparer_status(identity):
    return 'Ya' if identity.get('wellsite_prepared') is True else 'Belum dicatat (laporan lama)'

def setup_fonts():
    from reportlab.pdfbase.pdfmetrics import registerFont,getRegisteredFontNames
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab
    font_dir=Path(reportlab.__file__).parent/'fonts'
    with XML_LOCK:
        for name,file in (('DDR-Regular','Vera.ttf'),('DDR-Bold','VeraBd.ttf')):
            if name not in getRegisteredFontNames():registerFont(TTFont(name,str(font_dir/file)))

@lru_cache(maxsize=1)
def template_layout():
    return json.loads((ROOT/'templates/ddr-layout.json').read_text())

def activity_paragraph(text):
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    setup_fonts()
    return Paragraph(escape(str(text)).replace('\n','<br/>'),ParagraphStyle('activity',fontName='DDR-Regular',fontSize=11,leading=13,splitLongWords=1,wordWrap='CJK'))

def activity_height(text):
    layout=template_layout()
    width=sum((w*7+5)*.75 for w in layout['widths'][9:19])
    _,height=activity_paragraph(text).wrap(width-6,10000)
    return max(layout['heights'][45],height+6)

def activity_chunks(activities):
    # Preserve the supplied form while keeping long notes legible. A new form
    # page starts before enlarged activity rows add over 120 points of height.
    chunks=[];chunk=[];extra=0;baseline=template_layout()['heights'][45]
    for item in activities:
        growth=activity_height(activity_text(item))-baseline
        if chunk and (len(chunk)>=17 or extra+growth>120):
            chunks.append(chunk);chunk=[];extra=0
        chunk.append(item);extra+=growth
    if chunk:chunks.append(chunk)
    return chunks or [[]]

def page_heights(values):
    heights=list(template_layout()['heights'])
    heights[11]=max(heights[11],32)
    for row in range(46,63):
        if 'J'+str(row) in values:heights[row-1]=activity_height(values['J'+str(row)])
    return heights

def pages(report):
    d=ddr_rules.detail(report);ident=d.get('identity',{});move=d.get('movement',{})
    # Main sheet preserves the supplied form. Additional sheets repeat its grid.
    spec=[('open_holes',6,18,['H','I','J','K'],['from','to','interval','lithology']),('runs',16,27,['H','I','J','K','M','N','O','P','R'],['run','from','to','cored','recovered','recovery_pct','core_loss','rqd_pct','comment']),('lost_tools',3,21,['M','O','R','S'],['tool','size','qty','remark']),('activities',17,46,['H','I','J','T'],['from','to','name','hours'])]
    chunks=activity_chunks(d.get('activities',[]))
    count=max([len(chunks)]+[math.ceil(len(d.get(k,[]))/cap) for k,cap,*_ in spec if k!='activities']);out=[]
    hourly={name:sum(minutes(a) for a in d.get('activities',[]) if a['name']==name)/60 for names in ddr_detail.ACTIVITIES.values() for name in names}
    hours_rows=[20,21,*range(24,29),*range(31,45),*range(47,61),*range(66,72)]
    names=[n for items in ddr_detail.ACTIVITIES.values() for n in items]
    for page in range(count):
        values={'H72':'Driller','L72':'Wellsite','E9':report['work_date'],'E10':datetime.strptime(report['work_date'],'%Y-%m-%d').strftime('%A'),'E11':report['shift'],'E12':ident.get('geologist',''),'E13':ident.get('assistant_geologist',''),'E14':ident.get('azimuth','')+' / '+ident.get('dip',''),'P9':report.get('location',''),'P10':ident.get('hole',''),'P11':report.get('rig',''),'P12':ident.get('driller',''),'P13':ident.get('crew',''),'N17':move.get('from_hole',''),'P17':move.get('to_hole',''),'S17':move.get('distance_m',0),'F72':sum(hourly.values()),'Q2':f"DDR #{report['id']} / Rev {report.get('revision',0)}",'Q4':report.get('status',''),'Q6':f'Form {page+1}/{count} + Lampiran'}
        values['B12']='Wellsite Geologist /\nGeotech'
        for row,name in zip(hours_rows,names):values['F'+str(row)]=round(hourly[name],2)
        for k,c in zip(ddr_detail.CONSUMABLES,['J','K','M','N','O','P','R','S','T']):values[c+'66']=d.get('consumables',{}).get(k,0)
        for kind,cap,start,cols,keys in spec:
            items=(chunks[page] if page<len(chunks) else []) if kind=='activities' else d.get(kind,[])[page*cap:(page+1)*cap]
            for i,item in enumerate(items):
                for c,key in zip(cols,keys):values[c+str(start+i)]=activity_text(item) if kind=='activities' and key=='name' else item.get(key,'')
        out.append(values)
    return out

def appendix(report):
    d=ddr_rules.detail(report);units=d.get('units',{});red=d.get('redrill',{})
    # Metadata and full free text are retained here; compact form cells may abbreviate.
    rows=[['Section','Item / time','Field','Value'],['DDR',str(report['id']),'Revision / status',f"{report.get('revision',0)} / {report.get('status','')}"],['DDR','','Creator',report.get('operator','')],['Depth','','Start / end (m)',f"{report['start_depth']} / {report['end_depth']}"],['Hours','','DDR start / end',report['start_time']+' / '+report['end_time']],['Work','','Type / parent',red.get('kind','Normal')+' / '+red.get('parent','')],['Work','','Redrill reason',red.get('reason','')]]
    from ddr_metrics import commercial,hours,HOUR_LABELS
    summary=commercial(report)
    times,_=hours(report)
    for k,v in times.items():rows.append(['Waktu','',HOUR_LABELS[k]+' (jam)',round(v/60,4)])
    rows.append(['Tagihan','','Aturan recovery','Per run: <95% tarif Open Hole; >=95% tarif Coring. Aktivitas asli tetap tercatat.'])
    labels={'actual_m':'Total meter aktual','actual_oh_m':'Aktual Open Hole','actual_core_m':'Aktual Coring','tariff_oh_m':'OH + Coring recovery <95%','tariff_core_m':'Coring recovery >=95%','unclassified_m':'Meter perlu verifikasi','eligible_m':'Meter ditagih (status Billable)','nonbillable_m':'Meter tidak ditagih','pending_m':'Meter menunggu keputusan'}
    for key,label in labels.items():rows.append(['Rekap meter','',label+' (m)',summary[key]])
    rows.append(['Tagihan','','Status DDR',{'Billable':'Ditagih','Non-billable':'Tidak ditagih','Pending':'Perlu verifikasi'}.get(summary['billing'],'Perlu verifikasi')])
    rows.append(['Tagihan','','Tahap review',report.get('status','')])
    if summary['billing']=='Non-billable':rows.append(['Tagihan','','Nilai tagihan (Rp)',0])
    for run in summary['runs']:
        rows.append(['Tarif per run',f"{run['run']} / {run['from']:g}-{run['to']:g} m",'Recovery / kategori tarif',('Belum valid' if run['recovery_pct'] is None else f"{run['recovery_pct']:.4f}%")+' / '+run['tariff_category']])
    for warning in summary['issues']:rows.append(['Verifikasi','','Catatan',warning])
    for k,v in d.get('identity',{}).items():
        if k!='wellsite_prepared':rows.append(['Identity','',k,v])
    rows.append(['Identity','','Konfirmasi penyusun',preparer_status(d.get('identity',{}))])
    for kind,fields in [('open_holes',['lithology']),('runs',['run','comment']),('lost_tools',['tool','size','remark']),('activities',['name','note'])]:
        for i,item in enumerate(d.get(kind,[]),1):
            for k in fields:
                if item.get(k):rows.append([kind,i,k,item[k]])
    rows.extend([['Notes','','DDR note',report.get('note','')],['Review','','Reviewer',report.get('supervisor','') or ''],['Review','','Review note',report.get('review_note','') or '']])
    for i,x in enumerate(d.get('readings',[]),1):
        for k in ('wob','rpm','torque','pump_pressure'):
            if x.get(k) is not None:rows.append(['Parameter',f"{x['at']} / {x['activity']}",{'wob':'WOB','rpm':'RPM','torque':'Torque','pump_pressure':'Pump pressure'}[k]+' ('+('rpm' if k=='rpm' else units.get(k,''))+')',x[k]])
    if not d:rows.append(['Legacy','','Notice','Laporan lama tidak memiliki detail form. Nilai ringkasan tetap ditampilkan.'])
    for k in ('bit_used','rod_used','mud_used','wob','rpm','torque','pump_pressure'):
        if report.get(k) not in ('',None,0):rows.append(['Other / legacy','',k,report[k]])
    labels={'DDR':'DDR','Hours':'Hours','Work':'Pekerjaan','Identity':'Identity','open_holes':'Open Hole','runs':'Core run','lost_tools':'Lost tool','activities':'Drilling activity','effective':'Effective working','standby':'Standby / non-productive','maintenance':'Repair / maintenance','hole':'Drillhole No.','geologist':'Wellsite Geologist / Geotech','preparer_confirmed_by':'Dikonfirmasi oleh','preparer_confirmed_at':'Waktu konfirmasi','Creator':'Diinput oleh','assistant_geologist':'Assistant Geos','driller':'Driller','crew':'Drilling Crew','azimuth':'Azimuth','dip':'Dip','day':'Day','lithology':'Lith','run':'Run No.','comment':'Comment','tool':'Loss Tool','size':'Size','remark':'Remark','name':'Activity','note':'Note','bit_used':'Bit / equipment','rod_used':'Rod used (pcs)','mud_used':'Mud used (kg)'}
    full=[]
    for row in rows:
        row=[labels.get(str(v),v) if i in (0,2) else v for i,v in enumerate(row)]
        value=row[3]
        if isinstance(value,str) and len(value)>600:
            for offset in range(0,len(value),600):full.append([row[0],row[1],row[2]+(' (continued)' if offset else ''),value[offset:offset+600]])
        else:full.append(row)
    return full

def setcell(root,addr,value):
    sd=root.find(tag('sheetData'));rn=int(re.search(r'\d+',addr)[0]);row=sd.find(f"{tag('row')}[@r='{rn}']")
    if row is None:row=E.SubElement(sd,tag('row'),r=str(rn))
    cell=row.find(f"{tag('c')}[@r='{addr}']")
    if cell is None:cell=E.SubElement(row,tag('c'),r=addr)
    for child in list(cell):cell.remove(child)
    cell.attrib.pop('t',None)
    if isinstance(value,(float,int)):
        E.SubElement(cell,tag('v')).text=str(round(value,6))
    else:
        cell.set('t','inlineStr');s=E.SubElement(cell,tag('is'));t=E.SubElement(s,tag('t'));t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
        t.text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value if value is not None else ''))

def xlsx(report):
    with zipfile.ZipFile(ROOT/'templates/ddr.xlsx') as z:files={n:z.read(n) for n in z.namelist()}
    styles=E.fromstring(files['xl/styles.xml']);fonts=styles.find(tag('fonts'));font_id=len(fonts);font=E.SubElement(fonts,tag('font'));E.SubElement(font,tag('sz'),val='10');E.SubElement(font,tag('name'),val='Arial');fonts.set('count',str(len(fonts)))
    formats=styles.find(tag('cellXfs'));wrap_style=len(formats);fmt=E.SubElement(formats,tag('xf'),numFmtId='0',fontId=str(font_id),fillId='0',borderId='0',xfId='0',applyAlignment='1',applyFont='1');E.SubElement(fmt,tag('alignment'),vertical='top',wrapText='1');formats.set('count',str(len(formats)));files['xl/styles.xml']=xml(styles)
    shared_strings=[''.join(el.itertext()) for el in E.fromstring(files.get('xl/sharedStrings.xml',('<sst xmlns="'+NS+'"/>').encode()))]
    template=E.fromstring(files['xl/worksheets/sheet1.xml']);wb=E.fromstring(files['xl/workbook.xml']);sheets=wb.find(tag('sheets'));sheets.clear()
    defs=wb.find(tag('definedNames'))
    if defs is not None:wb.remove(defs)
    defs=E.SubElement(wb,tag('definedNames'))
    rels=E.fromstring(files['xl/_rels/workbook.xml.rels'])
    for r in list(rels):
        if r.get('Type','').endswith('/worksheet'):rels.remove(r)
    types=E.fromstring(files['[Content_Types].xml'])
    for el in list(types):
        if '/worksheets/' in el.get('PartName','') or '/drawings/' in el.get('PartName',''):types.remove(el)
    for name in list(files):
        if name.startswith(('xl/worksheets/','xl/drawings/','xl/media/')):del files[name]
    files['xl/media/mms.png']=(ROOT/'static/mms-logo.png').read_bytes()
    if not any(e.get('Extension')=='png' for e in types):E.SubElement(types,'{'+CT+'}Default',Extension='png',ContentType='image/png')
    vals=pages(report);total=len(vals)+1
    for i in range(1,total+1):
        main=i<=len(vals);name='DDR' if i==1 else ('DDR '+str(i) if main else 'Lampiran')
        if main:
            root=copy.deepcopy(template)
            for addr,v in vals[i-1].items():
                if re.fullmatch(r'N(?:2[7-9]|3[0-9]|4[0-2])',addr) and isinstance(v,(int,float)):v/=100
                setcell(root,addr,v)
            # Keep the form's existing borders while wrapping the new activity
            # descriptions and the expanded preparer label.
            wrapped={}
            for addr in ['B12','Q2','Q4','Q6']+[f'J{row}' for row in range(46,63) if f'J{row}' in vals[i-1]]:
                cell=root.find(tag('sheetData')).find(f"{tag('row')}/{tag('c')}[@r='{addr}']")
                if cell is None:continue
                old=int(cell.get('s','0'));key=(old,addr=='B12',addr.startswith('Q'))
                if key not in wrapped:
                    style=copy.deepcopy(formats[old])
                    alignment=style.find(tag('alignment'))
                    if alignment is None:alignment=E.SubElement(style,tag('alignment'))
                    alignment.set('wrapText','1');alignment.set('vertical','center');style.set('applyAlignment','1')
                    if addr!='B12':style.set('fontId',str(font_id));style.set('applyFont','1')
                    if addr.startswith('Q'):alignment.set('horizontal','center')
                    wrapped[key]=len(formats);formats.append(style)
                cell.set('s',str(wrapped[key]))
            compact={}
            for row in root.find(tag('sheetData')):
                for cell in row:
                    if not re.fullmatch(r'C(?:2[4-8]|3[1-9]|4[0-4]|4[7-9]|5[0-9]|60|6[6-9]|7[01])',cell.get('r','')):continue
                    text=''.join(cell.itertext())
                    if cell.get('t')=='s':text=shared_strings[int(text)]
                    if len(text)<24:continue
                    old=int(cell.get('s','0'))
                    if old not in compact:
                        style=copy.deepcopy(formats[old]);alignment=style.find(tag('alignment'))
                        if alignment is None:alignment=E.SubElement(style,tag('alignment'))
                        alignment.set('shrinkToFit','1');alignment.set('wrapText','0');style.set('applyAlignment','1')
                        compact[old]=len(formats);formats.append(style)
                    cell.set('s',str(compact[old]))
            for rn,height in enumerate(page_heights(vals[i-1]),1):
                row=root.find(tag('sheetData')).find(f"{tag('row')}[@r='{rn}']")
                if row is not None:row.set('ht',str(height));row.set('customHeight','1')
            # Simplify shift field and merge header metadata without old checkboxes.
            merges=root.find(tag('mergeCells'))
            for area in ('Q2:T3','Q4:T5','Q6:T7','P9:T9','P11:T11','P13:T13','B12:D12'):
                E.SubElement(merges,tag('mergeCell'),ref=area)
            merges.set('count',str(len(merges)))
            extent='A1:T73';last=73
        else:
            root=E.Element(tag('worksheet'));views=E.SubElement(root,tag('sheetViews'));E.SubElement(views,tag('sheetView'),workbookViewId='0',showGridLines='0')
            cols=E.SubElement(root,tag('cols'))
            for c,w in enumerate((22,32,28,80),1):E.SubElement(cols,tag('col'),min=str(c),max=str(c),width=str(w),customWidth='1')
            E.SubElement(root,tag('sheetData'))
            for rn,row in enumerate(appendix(report),1):
                for cn,v in enumerate(row,1):setcell(root,col(cn)+str(rn),v)
                el=root.find(tag('sheetData')).find(f"{tag('row')}[@r='{rn}']");el.set('ht',str(max(24,max(math.ceil(len(str(v))/w) for v,w in zip(row,[20,30,26,70]))*15)));el.set('customHeight','1')
                for cell in el:cell.set('s',str(wrap_style))
            last=len(appendix(report));extent=f'A1:D{last}'
        for n in ('drawing','legacyDrawing','legacyDrawingHF','pageMargins','pageSetup','headerFooter','printOptions','sheetPr'):
            for el in root.findall(tag(n)):root.remove(el)
        pr=E.Element(tag('sheetPr'));E.SubElement(pr,tag('pageSetUpPr'),fitToPage='1');root.insert(0,pr)
        # OOXML children must be ordered to avoid repair prompts in Excel.
        E.SubElement(root,tag('printOptions'),horizontalCentered='1')
        E.SubElement(root,tag('pageMargins'),left='0.25',right='0.25',top='0.3',bottom='0.4' if main else '0.3',header='0.1',footer='0.1')
        E.SubElement(root,tag('pageSetup'),paperSize='8' if main else '9',orientation='portrait',fitToWidth='1',fitToHeight='1' if main else '0')
        hf=E.SubElement(root,tag('headerFooter'));E.SubElement(hf,tag('oddFooter')).text=f'&LMMS DDR #{report["id"]} / rev {report.get("revision",0)}&R&P / &N'
        if main:
            status=preparer_status(ddr_rules.detail(report).get('identity',{}))
            actor=str(report.get('operator','')).replace('&','&&')
            hf.find(tag('oddFooter')).text=f'&L&8MMS DDR #{report["id"]} / rev {report.get("revision",0)}\nKonfirmasi penyusun: {status}. Diinput oleh: {actor}.&R&8&P / &N'
        if main:
            E.SubElement(root,tag('drawing'),{'{'+REL+'}id':'rIdMMS'})
            drawing=f'''<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{REL}"><xdr:oneCellAnchor><xdr:from><xdr:col>1</xdr:col><xdr:colOff>140000</xdr:colOff><xdr:row>1</xdr:row><xdr:rowOff>100000</xdr:rowOff></xdr:from><xdr:ext cx="1450000" cy="750000"/><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="MMS logo"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rIdLogo"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor></xdr:wsDr>'''
            files[f'xl/drawings/drawing{i}.xml']=drawing.encode()
            files[f'xl/drawings/_rels/drawing{i}.xml.rels']=f'<Relationships xmlns="{PKG}"><Relationship Id="rIdLogo" Type="{REL}/image" Target="../media/mms.png"/></Relationships>'.encode()
            files[f'xl/worksheets/_rels/sheet{i}.xml.rels']=f'<Relationships xmlns="{PKG}"><Relationship Id="rIdMMS" Type="{REL}/drawing" Target="../drawings/drawing{i}.xml"/></Relationships>'.encode()
            E.SubElement(types,'{'+CT+'}Override',PartName=f'/xl/drawings/drawing{i}.xml',ContentType='application/vnd.openxmlformats-officedocument.drawing+xml')
        # Maintain row/cell order after filling previously empty slots.
        sd=root.find(tag('sheetData'))
        for row in sd:
            row[:]=sorted(row,key=lambda c:(len(re.sub(r'\d','',c.get('r',''))),re.sub(r'\d','',c.get('r',''))))
        sd[:]=sorted(sd,key=lambda r:int(r.get('r')))
        files[f'xl/worksheets/sheet{i}.xml']=xml(root)
        E.SubElement(sheets,tag('sheet'),{'name':name,'sheetId':str(i),'{'+REL+'}id':'rIdSheet'+str(i)})
        E.SubElement(rels,'{'+PKG+'}Relationship',Id='rIdSheet'+str(i),Type=REL+'/worksheet',Target=f'worksheets/sheet{i}.xml')
        E.SubElement(types,'{'+CT+'}Override',PartName=f'/xl/worksheets/sheet{i}.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
        E.SubElement(defs,tag('definedName'),name='_xlnm.Print_Area',localSheetId=str(i-1)).text=f"'{name}'!$A$1:${'T' if main else 'D'}${last}"
    formats.set('count',str(len(formats)));files['xl/styles.xml']=xml(styles)
    files['xl/workbook.xml']=xml(wb);files['xl/_rels/workbook.xml.rels']=xml(rels);files['[Content_Types].xml']=xml(types)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for k,v in files.items():z.writestr(k,v)
    return out.getvalue()

def pdf(report):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A3,A4
    from reportlab.pdfbase.pdfmetrics import stringWidth
    setup_fonts()
    from reportlab.platypus import Table,TableStyle,Paragraph,SimpleDocTemplate
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from pypdf import PdfReader,PdfWriter
    layout=template_layout();widths=[(w*7+5)*.75 for w in layout['widths']];xs=[0]
    for w in widths:xs.append(xs[-1]+w)
    out=io.BytesIO();c=canvas.Canvas(out,pagesize=A3);c.setTitle(f"MMS DDR #{report['id']}");c.setAuthor('MMS Drilling')
    merges={(a,b):(z,d) for a,b,z,d in layout['merges']};merges.update({(r,17):(r+1,20) for r in (2,4,6)});merges.update({(r,16):(r,20) for r in (9,11,13)});merges.update({(r,2):(r,6) for r in (19,23,30,46,65)});merges[(12,2)]=(12,4)
    covered={(r,col) for (a,b),(z,d) in merges.items() for r in range(a,z+1) for col in range(b,d+1) if (r,col)!=(a,b)}
    pageset=pages(report)
    for page,values in enumerate(pageset,1):
        ys=[0]
        for h in page_heights(values):ys.append(ys[-1]+h)
        scale=min((A3[0]-36)/xs[-1],(A3[1]-60)/ys[-1])
        c.saveState();c.translate((A3[0]-xs[-1]*scale)/2,A3[1]-22);c.scale(scale,scale)
        cells={(x['row'],x['col']):x for x in layout['cells']}
        for addr,value in values.items():
            rn=int(re.search(r'\d+',addr)[0]);letters=re.sub(r'\d','',addr);cn=0
            for ch in letters:cn=cn*26+ord(ch)-64
            cells.setdefault((rn,cn),{'row':rn,'col':cn,'bold':False,'size':11,'align':'left','border':[False]*4})
            cells[(rn,cn)]={**cells[(rn,cn)],'value':value}
        for (r,k),cell in cells.items():
            if (r,k) in covered:continue
            x=xs[k-1];y=-ys[r-1];rr,kk=merges.get((r,k),(r,k));w=xs[kk]-xs[k-1];h=ys[rr]-ys[r-1]
            c.setStrokeColor(colors.HexColor('#47524c'));c.setLineWidth(.45)
            borders=cell['border']
            if (r,k) in merges:
                borders=[any(cells.get((rn,k),{}).get('border',[False]*4)[0] for rn in range(r,rr+1)),any(cells.get((rn,kk),{}).get('border',[False]*4)[1] for rn in range(r,rr+1)),any(cells.get((r,cn),{}).get('border',[False]*4)[2] for cn in range(k,kk+1)),any(cells.get((rr,cn),{}).get('border',[False]*4)[3] for cn in range(k,kk+1))]
            for on,pts in zip(borders,[(x,y,x,y-h),(x+w,y,x+w,y-h),(x,y,x+w,y),(x,y-h,x+w,y-h)]):
                if on:c.line(*pts)
            value=cell.get('value')
            if value in (None,''):continue
            if k==10 and 46<=r<=62 and 'J'+str(r) in values:
                paragraph=activity_paragraph(value);_,ph=paragraph.wrap(w-6,h-4)
                paragraph.drawOn(c,x+3,y-(h+ph)/2)
                continue
            if (r,k)==(12,2):
                paragraph=Paragraph(escape(str(value)).replace('\n','<br/>'),ParagraphStyle('preparer',fontName='DDR-Bold',fontSize=9,leading=11))
                _,ph=paragraph.wrap(w-5,h-4);paragraph.drawOn(c,x+2,y-(h+ph)/2)
                continue
            text=(f'{value:g}' if isinstance(value,(int,float)) else str(value)).replace('\n',' ')
            size=min(cell['size'],20);font='DDR-Bold' if cell['bold'] else 'DDR-Regular'
            if r<8 and k==17:size=10
            if (r,k) in ((16,2),(16,6),(17,8),(17,9),(17,10),(64,15),(43,3),(48,3)):size=9
            if r in (19,23,30,46,65) and k==2:size=11
            if (r,k) not in merges and not any(borders):
                # Excel allows labels to flow over adjacent empty unbordered cells.
                while kk<20 and not cells.get((r,kk+1),{}).get('value') and (r,kk+1) not in covered and not any(cells.get((r,kk+1),{}).get('border',[False]*4)):
                    kk+=1;w=xs[kk]-xs[k-1]
            from reportlab.lib.utils import simpleSplit
            lines=simpleSplit(text,font,size,max(4,w-5)) if h>=28 else [text]
            maxlines=max(1,int((h-3)/(size+1)))
            lines=lines[:maxlines]
            for j,line in enumerate(lines):
                if stringWidth(line,font,size)>w-5:
                    while stringWidth(line+'…',font,size)>w-5 and line:line=line[:-1]
                    line+='…'
                c.setFont(font,size);c.setFillColor(colors.HexColor('#14271b'))
                tx=x+2 if cell.get('align')!='center' else x+w/2-stringWidth(line,font,size)/2
                c.drawString(tx,y-h/2+(len(lines)-1)*(size+1)/2-j*(size+1)-size*.34,line)
        c.drawImage(ImageReader(str(ROOT/'static/mms-logo.png')),xs[1]+12,-ys[7]+10,width=xs[5]-xs[1]-24,height=ys[7]-ys[1]-20,preserveAspectRatio=True,anchor='c',mask='auto')
        c.restoreState();c.setFont('DDR-Regular',8);c.setFillColor(colors.HexColor('#455d4c'));c.drawString(20,13,f"MMS DDR #{report['id']} / revision {report.get('revision',0)} / {report.get('status','')} · Form {page}/{len(pageset)} · Full notes and parameter readings: appendix")
        identity=ddr_rules.detail(report).get('identity',{})
        stamp=f"Konfirmasi penyusun: {preparer_status(identity)}. Diinput oleh: {report.get('operator','')}."
        while stringWidth(stamp,'DDR-Regular',8)>A3[0]-40:stamp=stamp[:-2]+'…'
        c.drawString(20,25,stamp)
        c.showPage()
    c.save()
    # Appendix uses A4 with wrapping/repeated headers; text never disappears from the download.
    more=io.BytesIO();style=ParagraphStyle('data',fontName='DDR-Regular',fontSize=8,leading=11,wordWrap='CJK')
    rows=[[Paragraph(escape(str(v)).replace('\n','<br/>'),style) for v in row] for row in appendix(report)]
    table=Table(rows,colWidths=[78,106,105,246],repeatRows=1,hAlign='LEFT');table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4eee7')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#344e3e')),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#d5ddd7')),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    def footer(cv,doc):
        cv.setFont('DDR-Regular',8);cv.drawString(30,18,f"MMS DDR #{report['id']} / revision {report.get('revision',0)} · Appendix {doc.page}")
    SimpleDocTemplate(more,pagesize=A4,leftMargin=30,rightMargin=30,topMargin=30,bottomMargin=32).build([Paragraph(f"DDR #{report['id']} · Rekap, tarif dan catatan",ParagraphStyle('title',fontName='DDR-Bold',fontSize=13,spaceAfter=15)),table],onFirstPage=footer,onLaterPages=footer)
    writer=PdfWriter()
    for raw in (out,more):
        for page in PdfReader(io.BytesIO(raw.getvalue())).pages:writer.add_page(page)
    result=io.BytesIO();writer.write(result);return result.getvalue()

def export(report,kind):
    if kind=='xlsx':return xlsx(report),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    if kind=='pdf':return pdf(report),'application/pdf'
    raise ValueError('Format unduhan tidak dikenal')
