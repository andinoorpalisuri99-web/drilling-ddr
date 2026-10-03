/* Calendar targets and server-side dashboard totals. */
(() => {
  const $plan=s=>document.querySelector(s);
  let dashboardRequest=0,planRequest=0,reportsRequest=0,currentPlan=null;
  const periodKey=(period,date)=>period==='Daily'?date:period==='Monthly'?date.slice(0,7):date.slice(0,4);
  const dateValue=()=>today();
  function setPicker(input,period,old){
    input.type=period==='Daily'?'date':period==='Monthly'?'month':'number';
    if(period==='Yearly'){input.min='1000';input.max='9998';input.step='1';}
    input.value=periodKey(period,old||dateValue());
  }
  function pickerLabel(period){return ({Daily:'HARIAN',Monthly:'BULANAN',Yearly:'TAHUNAN'})[period]}
  let latestWorkDate=null;
  const displayDate=value=>new Intl.DateTimeFormat('id-ID',{dateStyle:'long'}).format(new Date(value+'T12:00:00'));
  const compactDate=value=>new Intl.DateTimeFormat('id-ID',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value+'T12:00:00'));
  function periodLabel(period,key){
    if(!key)return '';
    if(period==='Yearly')return `Tahunan · ${key}`;
    if(period==='Monthly')return `Bulanan · ${new Intl.DateTimeFormat('id-ID',{month:'long',year:'numeric'}).format(new Date(key+'-01T12:00:00'))}`;
    return `Harian · ${compactDate(key)}`;
  }
  function headerContext(){
    const inDashboard=!$plan('#dashboard').classList.contains('hidden');
    const label=inDashboard?periodLabel($plan('#dashboardPeriod').value,$plan('#dateFilter').value):'';
    $plan('#headerPeriod').textContent=label;
    $plan('#floatingPeriod').textContent=label;
    $plan('#floatingTitle').textContent=$plan('#pageTitle').textContent;
    $plan('#mobileContext').textContent=inDashboard&&label?'Overview · '+label:'MMS MINING EXPLORATION';
  }
  function showFreshness(data){
    const notice=$plan('#dataFreshness'),status=$plan('#dataStatusLine'),empty=data.report_count===0;
    latestWorkDate=data.freshness?.latest_work_date||null;
    notice.classList.toggle('hidden',!empty);
    status.classList.toggle('hidden',empty);
    const saved=data.freshness?.latest_saved_at;
    const savedLabel=saved?new Intl.DateTimeFormat('id-ID',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Makassar'}).format(new Date(saved))+' WITA':'';
    status.textContent=latestWorkDate?`DDR terbaru ${compactDate(latestWorkDate)}${savedLabel?' · Tersimpan '+savedLabel:''}`:'DDR pada periode terpilih sudah tersedia.';
    if(!empty)return;
    $plan('#freshnessTitle').textContent=data.period==='Daily'&&data.period_key===dateValue()?'Belum ada DDR hari ini':`Belum ada DDR ${periodLabel(data.period,data.period_key)}`;
    $plan('#freshnessDetail').textContent=latestWorkDate?`Data terakhir: ${compactDate(latestWorkDate)}`:'Belum ada DDR tersimpan di server';
    $plan('#showLatestData').classList.toggle('hidden',!latestWorkDate);
  }
  $plan('#showLatestData').addEventListener('click',()=>{
    if(!latestWorkDate)return;
    $plan('#dashboardPeriod').value='Daily';setPicker($plan('#dateFilter'),'Daily',latestWorkDate);renderDashboard();
  });
  async function renderDashboard(){
    if(window.DDRAnalytics){headerContext();return window.DDRAnalytics.renderDashboard();}
    if(Offline.isOffline)return;
    const who=typeof session==='undefined'?null:session?.username;
    const request=++dashboardRequest,period=$plan('#dashboardPeriod').value,key=$plan('#dateFilter').value;
    headerContext();
    $plan('#dataFreshness').classList.add('hidden');$plan('#dataStatusLine').classList.add('hidden');latestWorkDate=null;
    if(!key)return;
    if(typeof session!=='undefined' && session?.role==='operator' && window.renderPersonalDashboard)return window.renderPersonalDashboard();
    try{
      const data=await api(`/api/targets/period?period=${encodeURIComponent(period)}&key=${encodeURIComponent(key)}`);
      if(request!==dashboardRequest||(typeof session!=='undefined'&&session?.username!==who))return;
      showFreshness(data);
      if(window.renderHoursSummary)window.renderHoursSummary();
      $plan('#targetMetricLabel').textContent='TARGET '+pickerLabel(period);
      $plan('#totalMeters').innerHTML=`${fmt(data.actual_m)} <small>m</small>`;
      $plan('#totalTarget').innerHTML=`${fmt(data.total_target_m)} <small>m</small>`;
      const percent=data.report_count?data.achievement_pct:null;
      $plan('#achievement').className=percent==null?'':progressState(percent);
      $plan('#achievement').innerHTML=percent==null?'—':`${fmt(percent)} <small>%</small>`;
      $plan('#totalDowntime').innerHTML=`${fmt(data.downtime_min/60)} <small>jam</small>`;
      $plan('#rigProgress').innerHTML=data.rigs.map(r=>`<div class="rigline"><b>${esc(r.rig)}</b><div class="track"><div class="fill ${r.achievement_pct==null?'':progressState(r.achievement_pct)}" style="width:${r.achievement_pct==null?0:Math.min(100,Math.max(0,r.achievement_pct))}%"></div></div><span>${fmt(r.actual_m)} / ${r.target_m==null?'—':fmt(r.target_m)} m</span></div>`).join('');
      $plan('#reportCount').textContent=`${data.report_count} laporan`;
      $plan('#recent').textContent='';const activity=document.createElement('p');activity.className='empty';activity.textContent=data.report_count?`${data.pending_count} DDR menunggu review. Lihat daftar DDR untuk rincian laporan.`:(latestWorkDate?'Belum ada DDR pada periode ini. Pilih data terbaru untuk melihat laporan yang tersedia.':'Belum ada DDR Submitted atau Approved yang tersimpan di server.');$plan('#recent').append(activity);
      $plan('#dashboardCoverage').textContent=`Periode ${data.start} sampai sebelum ${data.end}. ${data.missing_count?'Ada '+data.missing_count+' rig tanpa target atau target 0; persentase total tidak dihitung.':'Semua rig memiliki target di atas 0.'} Target yang belum diatur mengikuti rencana dasar per rig. DDR Submitted dan Approved dihitung; Rejected tidak dihitung.`;
    }catch(err){if(request===dashboardRequest)$plan('#dashboardCoverage').textContent='Ringkasan gagal dimuat: '+err.message}
  }
  window.showDDRFreshness=showFreshness;
  window.renderDashboard=renderDashboard;
  window.renderReports=async function(more=false){
    if(Offline.isOffline)return;
    more=more===true;
    const who=session?.username;
    const request=++reportsRequest,date=$plan('#reportDate').value,rig=$plan('#rigFilter').value;
    if(!more)$plan('#reportRows').innerHTML='<tr><td colspan="8" class="empty">Memuat DDR…</td></tr>';
    $plan('#moreReports').disabled=true;
    try{
      const query=new URLSearchParams({limit:'200',offset:String(more?reports.length:0)});if(date)query.set('date',date);if(rig)query.set('rig',rig);
      const rows=await api('/api/reports?'+query);
      if(request!==reportsRequest||session?.username!==who)return;
      reports=more?reports.concat(rows):rows;
      $plan('#reportRows').innerHTML=reports.length?reports.map(r=>`<tr><td data-cell-label="Tanggal / shift">${esc(r.work_date)}<br><small>${esc(r.shift)} shift</small></td><td data-cell-label="Rig / hole">${esc(r.rig)}${r.rig_active===0?'<br><small class="archiveLabel">Rig nonaktif · arsip</small>':''}<br><small>${esc(r.hole_code||r.ddr_detail?.identity?.hole||"—")}</small></td><td data-cell-label="Kedalaman">${fmt(r.start_depth)} – ${fmt(r.end_depth)} m</td><td data-cell-label="Meter"><strong>${fmt(r.end_depth-r.start_depth)} m</strong></td><td data-cell-label="Breakdown / perawatan">${r.downtime_min} min</td><td data-cell-label="Teknisi">${esc(r.operator)}</td><td data-cell-label="Status"><span class="status ${esc(r.status)}">${esc(r.status)}</span></td><td data-cell-label="Laporan"><button data-detail="${r.id}">Detail</button></td></tr>`).join(''):'<tr><td colspan="8" class="empty">Tidak ada DDR pada filter ini.</td></tr>';
      $plan('#moreReports').classList.toggle('hidden',rows.length<200);
      $plan('#moreReports').disabled=false;
    }catch(err){if(request===reportsRequest){$plan('#moreReports').disabled=false;$plan('#reportRows').innerHTML=`<tr><td colspan="8" class="empty">${esc(err.message)}</td></tr>`}}
  };
  $plan('#moreReports').addEventListener('click',()=>renderReports(true));
  const baseView=view;
  window.view=function(id){baseView(id);headerContext();if(id==='targetsView')loadPeriodPlan();if(id==='dashboard'&&!Offline.isOffline)renderDashboard()};
  const baseToday=$plan('#today').onclick;
  $plan('#today').onclick=()=>{setPicker($plan('#dateFilter'),$plan('#dashboardPeriod').value,dateValue());renderDashboard()};
  $plan('#dashboardPeriod').addEventListener('change',()=>{setPicker($plan('#dateFilter'),$plan('#dashboardPeriod').value,dateValue());renderDashboard()});
  headerContext();

  function updateSelected(){
    if(!currentPlan)return;
    const row=currentPlan.rigs.find(r=>String(r.rig_id)===$plan('#periodPlanRig').value);
    if(!row)return;
    $plan('#periodPlanValue').value=row.target_m??'';
    $plan('#periodPlanRevision').value=row.revision||0;
  }
  async function loadPeriodPlan(){
    const request=++planRequest,period=$plan('#periodPlanType').value,key=$plan('#periodPlanKey').value;
    if(!key)return;
    try{
      const data=await api(`/api/targets/period?period=${encodeURIComponent(period)}&key=${encodeURIComponent(key)}`);
      if(request!==planRequest)return;
      currentPlan=data;
      const selector=$plan('#periodPlanRig'),selected=selector.value;
      selector.innerHTML=data.rigs.map(r=>`<option value="${r.rig_id}">${esc(r.rig)} · ${esc(r.location)}</option>`).join('');
      if(data.rigs.some(r=>String(r.rig_id)===selected))selector.value=selected;
      updateSelected();
      $plan('#periodPlanCurrent').innerHTML=`<div class="panelhead"><h3>Target ${esc(period)} ${esc(key)}</h3><span>${data.report_count} DDR</span></div><div class="tablewrap"><table><thead><tr><th>Rig</th><th>Target</th><th>Aktual</th><th>Pencapaian</th><th>Sumber</th></tr></thead><tbody>${data.rigs.map(r=>`<tr><td data-cell-label="Rig / hole">${esc(r.rig)}${r.rig_active===0?'<br><small class="archiveLabel">Rig nonaktif · arsip</small>':''}<br><small>${esc(r.hole_code||r.ddr_detail?.identity?.hole||"—")}</small></td><td>${r.target_m==null?'—':fmt(r.target_m)+' m'}</td><td>${fmt(r.actual_m)} m</td><td>${r.achievement_pct==null?'—':fmt(r.achievement_pct)+'%'}</td><td>${esc(r.source)}</td></tr>`).join('')}</tbody></table></div>`;
      $plan('#periodPlanHistory').innerHTML=`<div class="panelhead"><h3>Riwayat revisi periode</h3><span>${data.history.length} terakhir</span></div><div class="tablewrap"><table><thead><tr><th>Waktu</th><th>Rig</th><th>Perubahan</th><th>Alasan</th><th>Akun</th></tr></thead><tbody>${data.history.length?data.history.map(h=>`<tr><td>${esc(h.at)}</td><td>${esc(h.rig)}</td><td>${h.old_target==null?'—':fmt(h.old_target)} → ${fmt(h.new_target)} m</td><td>${esc(h.reason)}</td><td>${esc(h.actor)}</td></tr>`).join(''):'<tr><td colspan="5">Belum ada revisi target periode.</td></tr>'}</tbody></table></div>`;
    }catch(err){if(request===planRequest)$plan('#periodPlanMessage').textContent=err.message}
  }
  $plan('#periodPlanType').addEventListener('change',e=>{setPicker($plan('#periodPlanKey'),e.target.value,dateValue());loadPeriodPlan()});
  $plan('#periodPlanKey').addEventListener('change',loadPeriodPlan);
  $plan('#periodPlanRig').addEventListener('change',updateSelected);
  $plan('#periodTargetForm').addEventListener('submit',async e=>{
    e.preventDefault();const message=$plan('#periodPlanMessage');message.textContent='';
    const data=Object.fromEntries(new FormData(e.target));
    try{await api('/api/targets/period',{method:'POST',body:JSON.stringify(data)});e.target.elements.reason.value='';await loadPeriodPlan();await renderDashboard();toast('Target periode dan riwayat revisi tersimpan')}
    catch(err){message.textContent=err.message}
  });
  setPicker($plan('#periodPlanKey'),'Daily',dateValue());
  $plan('#periodTargetForm').classList.toggle('hidden',!['admin','manager'].includes(session?.role));
  const sessionWatcher=new MutationObserver(()=>{$plan('#periodTargetForm').classList.toggle('hidden',!['admin','manager'].includes(session?.role))});
  sessionWatcher.observe($plan('#accountName'),{childList:true});
  $plan('#openPassword').addEventListener('click',()=>{$plan('#passwordMessage').textContent='';$plan('#passwordDialog').showModal()});
  $plan('#closePassword').addEventListener('click',()=>$plan('#passwordDialog').close());
  $plan('#passwordForm').addEventListener('submit',async e=>{
    e.preventDefault();const message=$plan('#passwordMessage');message.textContent='';
    try{await api('/api/account/password',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});e.target.reset();$plan('#passwordDialog').close();session=null;$plan('#loginGate').classList.remove('hidden');$plan('#loginMessage').textContent='Kata sandi berubah. Masuk kembali.'}
    catch(err){message.textContent=err.message}
  });
  $plan('#closeReset').addEventListener('click',()=>$plan('#resetDialog').close());
  document.addEventListener('click',async e=>{
    const reset=e.target.closest('[data-user-reset]');
    if(reset){$plan('#resetForm').reset();$plan('#resetUserId').value=reset.dataset.userReset;$plan('#resetMessage').textContent='';$plan('#resetDialog').showModal();return}
    const status=e.target.closest('[data-user-status]');if(!status)return;
    const [id,active]=status.dataset.userStatus.split(':');
    if(!confirm(active==='0'?'Nonaktifkan akun dan semua sesinya?':'Aktifkan kembali akun ini?'))return;
    try{await api('/api/users/status',{method:'POST',body:JSON.stringify({id,active:Number(active)})});await loadUsers();toast('Status akun tersimpan')}
    catch(err){toast(err.message)}
  });
  $plan('#resetForm').addEventListener('submit',async e=>{
    e.preventDefault();try{await api('/api/users/reset',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});e.target.reset();$plan('#resetDialog').close();toast('Kata sandi direset dan sesi akun dicabut')}
    catch(err){$plan('#resetMessage').textContent=err.message}
  });
})();
