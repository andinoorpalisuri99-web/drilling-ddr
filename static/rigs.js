/* Admin rig master. A linked rig can be retired while its history stays intact. */
(() => {
  const section=document.querySelector('#rigMasterView');
  const form=document.querySelector('#rigForm');
  const message=document.querySelector('#rigMasterMessage');
  let state={rigs:[],history:[]},request=0;

  function resetForm(){
    form.reset();form.elements.id.value='';form.elements.target_m.disabled=false;
    document.querySelector('#rigSeedLabel').classList.remove('hidden');
    document.querySelector('#rigFormTitle').textContent='Tambah rig';
    document.querySelector('#rigCancelEdit').classList.add('hidden');
    form.querySelector('button[type="submit"]').textContent='Simpan rig';
    message.textContent='';
  }
  function render(){
    document.querySelector('#rigList').innerHTML=`<div class="panelhead"><h3>Daftar rig</h3><span>${state.rigs.length} rig</span></div><div class="tablewrap"><table><thead><tr><th>Kode</th><th>Lokasi / area</th><th>Target dasar harian</th><th>Status</th><th>Aksi</th></tr></thead><tbody>${state.rigs.length?state.rigs.map(r=>`<tr><td><strong>${esc(r.code)}</strong></td><td>${esc(r.location)}</td><td>${fmt(r.target_m)} m</td><td><span class="rigStatus ${r.active?'isActive':'isInactive'}">${r.active?'Aktif':'Nonaktif'}</span></td><td class="rigActions"><button type="button" data-edit-rig="${r.id}">Edit</button><button type="button" data-toggle-rig="${r.id}">${r.active?'Nonaktifkan':'Aktifkan'}</button></td></tr>`).join(''):'<tr><td colspan="5" class="empty">Belum ada rig.</td></tr>'}</tbody></table></div>`;
    document.querySelector('#rigHistory').innerHTML=`<div class="panelhead"><h3>Riwayat master rig</h3><span>${state.history.length} catatan terakhir</span></div><div class="tablewrap"><table><thead><tr><th>Waktu (UTC)</th><th>Rig</th><th>Perubahan</th><th>Akun</th></tr></thead><tbody>${state.history.length?state.history.map(h=>{const current=JSON.parse(h.after_json),previous=h.before_json?JSON.parse(h.before_json):null;let change=h.action==='CREATED'?'Ditambahkan':h.action==='DEACTIVATED'?'Dinonaktifkan':h.action==='REACTIVATED'?'Diaktifkan':`Identitas: ${esc(previous?.code||'—')} / ${esc(previous?.location||'—')} → ${esc(current.code)} / ${esc(current.location)}`;return `<tr><td>${esc(h.at)}</td><td>${esc(current.code)}</td><td>${change}</td><td>${esc(h.actor)}</td></tr>`}).join(''):'<tr><td colspan="4" class="empty">Belum ada perubahan.</td></tr>'}</tbody></table></div>`;
  }
  window.loadRigMaster=async()=>{
    const current=++request;
    document.querySelector('#rigList').textContent='Memuat master rig…';
    try{const result=await api('/api/rigs/manage');if(current!==request)return;state=result;render()}
    catch(err){if(current===request)document.querySelector('#rigList').textContent='Master rig gagal dimuat: '+err.message}
  };
  section.addEventListener('click',async event=>{
    if(event.target.id==='rigCancelEdit'){resetForm();return}
    const edit=event.target.closest('[data-edit-rig]');
    if(edit){const rig=state.rigs.find(x=>String(x.id)===edit.dataset.editRig);if(!rig)return;
      resetForm();form.elements.id.value=rig.id;form.elements.code.value=rig.code;form.elements.location.value=rig.location;
      form.elements.target_m.disabled=true;document.querySelector('#rigSeedLabel').classList.add('hidden');
      document.querySelector('#rigFormTitle').textContent='Koreksi identitas rig';
      document.querySelector('#rigCancelEdit').classList.remove('hidden');
      form.querySelector('button[type="submit"]').textContent='Simpan koreksi';form.scrollIntoView({block:'start',behavior:'smooth'});return;
    }
    const toggle=event.target.closest('[data-toggle-rig]');if(!toggle)return;
    const rig=state.rigs.find(x=>String(x.id)===toggle.dataset.toggleRig);if(!rig)return;
    if(!confirm(rig.active?`Nonaktifkan ${rig.code}? Riwayat DDR tetap tersimpan, tetapi rig tidak dapat dipilih untuk Input shift baru.`:`Aktifkan kembali ${rig.code}?`))return;
    try{await api('/api/rigs/update',{method:'POST',body:JSON.stringify({id:rig.id,active:rig.active?0:1})});resetForm();await refresh();await window.loadRigMaster();toast('Status rig diperbarui')}
    catch(err){message.textContent=err.message}
  });
  form.addEventListener('submit',async event=>{
    event.preventDefault();message.textContent='';
    const data=Object.fromEntries(new FormData(form));
    const editing=!!data.id;
    try{await api(editing?'/api/rigs/update':'/api/rigs',{method:'POST',body:JSON.stringify(data)});
      resetForm();await refresh();await window.loadRigMaster();toast(editing?'Identitas rig diperbarui':'Rig baru ditambahkan')}
    catch(err){message.textContent=err.message}
  });
})();
