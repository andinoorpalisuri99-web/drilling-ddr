/* MMS spatial planning. Authenticated geometry is cached per account in IndexedDB,
   never in the public shell. Satellite tiles are online only and not precached. */
(() => {
 'use strict';
 const el=id=>document.getElementById(id);
 const number=(n,d=2)=>Number(n).toLocaleString('id-ID',{minimumFractionDigits:d,maximumFractionDigits:d});
 let map=null,boundary=null,pointsLayer=null,imagery=null,data=null,owner=null,selected=null,request=0,ready=false;
 let markers=new Map(),labels=false,plain=false,tileFailures=0;
 const imageryUrl='https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
 async function prime(user){
  const revision=++request;owner=user;
  try {
   let loaded;
   if(Offline.isOffline)loaded=await Offline.loadMap(user);
   else {
    try{loaded=await api('/api/drilling-map');await Offline.cacheMap(user,loaded).catch(()=>{});}
    catch(error){if(error instanceof TypeError)loaded=await Offline.loadMap(user);else throw error;}
   }
   if(revision!==request||session?.username!==user)return;
   data=loaded||null;
  } catch(error){if(revision===request)data=null;}
 }
 function state(text,error=false){const box=el('mapLoadState');box.textContent=text;box.classList.remove('hidden');box.classList.toggle('mapError',error);}
 async function show(){
  if(!session?.username)return;
  const user=session.username;
  if(owner!==user||!data){state('Memuat boundary dan titik rencana…');await prime(user);}
  if(session?.username!==user||el('mapView').classList.contains('hidden'))return;
  if(!data){state('Peta belum tersedia. Buka menu ini saat online untuk menyimpan boundary dan titik pada perangkat.',true);return;}
  if(!window.L){state('Komponen peta belum terpasang. Pasang seluruh isi patch lalu muat ulang.',true);return;}
  el('mapLoadState').classList.add('hidden');el('mapWorkspace').classList.remove('hidden');
  el('mapPointCount').textContent=data.points.length;
  el('mapArea').textContent=number(data.boundary.area_ha)+' ha';
  if(!map)createMap();
  map.invalidateSize();
  if(!ready){fitBoundary(false);ready=true;}
  if(Offline.isOffline||!navigator.onLine)setBasemap(true);
 }
 function icon(point,active=false){return L.divIcon({className:'mapPointIcon',iconSize:[28,28],iconAnchor:[14,14],html:`<span class="mapMarker${active?' selected':''}" data-point="${point.id}" aria-hidden="true"><i></i></span>`});}
 function createMap(){
  map=L.map('drillingMapCanvas',{zoomControl:false,minZoom:11,maxZoom:20,scrollWheelZoom:false,maxBoundsViscosity:0.8});
  L.control.zoom({position:'topleft',zoomInTitle:'Perbesar peta',zoomOutTitle:'Perkecil peta'}).addTo(map);
  L.control.scale({position:'bottomleft',imperial:false}).addTo(map);
  map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
  boundary=L.polygon(data.boundary.coordinates,{color:'#d5a53d',weight:2.5,fillColor:'#dbad45',fillOpacity:0.13,interactive:false}).addTo(map);
  pointsLayer=L.featureGroup().addTo(map);
  for(const point of data.points){
   const marker=L.marker(point.latlng,{icon:icon(point),title:point.id+' · Titik rencana sementara',alt:point.id,keyboard:true,riseOnHover:true});
   marker.on('click',()=>selectPoint(point.id,false));marker.addTo(pointsLayer);
   marker.bindTooltip(point.id,{direction:'top',offset:[0,-10],permanent:false,className:'mapTooltip'});
   markers.set(point.id,marker);
  }
  map.on('zoomend',()=>{if(labels)updateLabels()});
  map.setMaxBounds(boundary.getBounds().pad(1.5));
  imagery=L.tileLayer(imageryUrl,{maxNativeZoom:19,maxZoom:20,attribution:'Tiles © Esri · Sources: Esri, Vantor, Earthstar Geographics, and the GIS User Community'});
  imagery.on('tileerror',()=>{tileFailures++;if(!plain)el('mapImageStatus').textContent='Citra belum termuat. Coba Tanpa citra atau periksa koneksi.';});
  imagery.on('loading',()=>{tileFailures=0;if(!plain)el('mapImageStatus').textContent='Memuat citra satelit…';});
  imagery.on('load',()=>{if(!plain&&!tileFailures)el('mapImageStatus').textContent='Citra satelit · bukan kondisi lapangan live';});
  setBasemap(Offline.isOffline||!navigator.onLine);
  renderList();
 }
 function setBasemap(without){
  plain=without;el('mapSatellite').setAttribute('aria-pressed',String(!plain));el('mapPlain').setAttribute('aria-pressed',String(plain));
  if(!map)return;
  if(plain){if(map.hasLayer(imagery))map.removeLayer(imagery);el('mapImageStatus').textContent=(Offline.isOffline||!navigator.onLine)?'Offline · boundary dan titik tersimpan di perangkat.':'Boundary dan titik tanpa citra satelit.';}
  else {if(!navigator.onLine||Offline.isOffline){setBasemap(true);toast('Citra satelit memerlukan koneksi internet');return;}if(!map.hasLayer(imagery))imagery.addTo(map);el('mapImageStatus').textContent='Memuat citra satelit…';}
  el('drillingMapCanvas').classList.toggle('mapWithoutImage',plain);
 }
 function fitBoundary(animate=true){if(map)map.fitBounds(boundary.getBounds(),{padding:[32,36],maxZoom:16,animate});}
 function fitPoints(){if(map)map.fitBounds(L.latLngBounds(data.points.map(p=>p.latlng)),{padding:[38,42],maxZoom:17});}
 function updateLabels(){
  for(const [id,marker] of markers){const tooltip=marker.getTooltip();tooltip.options.permanent=labels&&map.getZoom()>=16;marker.closeTooltip();if(tooltip.options.permanent)marker.openTooltip();}
  el('mapLabelToggle').title=labels&&map.getZoom()<16?'Perbesar peta untuk menampilkan label tanpa menumpuk':'Label titik';
 }
 function renderList(){
  if(!data)return;
  const q=el('mapSearch').value.trim().toUpperCase();
  const rows=data.points.filter(p=>p.id.includes(q));
  el('mapListCount').textContent=rows.length+' / '+data.points.length+' lokasi';
  el('mapPointList').replaceChildren();
  for(const point of rows){
   const button=document.createElement('button');button.type='button';button.className='mapPointRow';button.dataset.mapPoint=point.id;
   button.setAttribute('aria-pressed',String(selected===point.id));button.innerHTML=`<span class="mapRowDot" aria-hidden="true"></span><span><strong>${point.id}</strong><small>Label sementara</small></span><span class="mapRowStatus">Rencana <b aria-hidden="true">›</b></span>`;
   button.onclick=()=>selectPoint(point.id,true);el('mapPointList').append(button);
  }
  if(!rows.length){const text=document.createElement('p');text.className='mapNoResults';text.textContent='Tidak ada titik yang sesuai.';el('mapPointList').append(text);}
 }
 function selectPoint(id,move){
  const point=data?.points.find(p=>p.id===id);if(!point)return;
  if(selected)markers.get(selected)?.setIcon(icon(data.points.find(p=>p.id===selected)));
  selected=id;el('mapSelectedLabel').textContent=id;el('mapSelectedPeek').classList.remove('hidden');const marker=markers.get(id);marker.setIcon(icon(point,true));marker.setZIndexOffset(500);
  for(const [key,other] of markers)if(key!==id)other.setZIndexOffset(0);
  if(!map.hasLayer(pointsLayer)){pointsLayer.addTo(map);el('mapPointToggle').checked=true;}
  if(move)map.setView(point.latlng,Math.max(map.getZoom(),17));
  marker.openTooltip();renderList();
  el('mapPointDetail').innerHTML=`<div class="mapDetailTop"><span class="mapEyebrow">DETAIL LOKASI</span><button id="mapClearSelection" type="button" aria-label="Tutup detail titik">×</button></div><h3>${point.id}<span>Label sementara</span></h3><span class="mapPlanBadge"><i></i>Rencana pengeboran</span><dl><div><dt>Easting / X</dt><dd>${number(point.easting)} m</dd></div><div><dt>Northing / Y</dt><dd>${number(point.northing)} m</dd></div><div><dt>Latitude</dt><dd>${number(point.latlng[0],6)}°</dd></div><div><dt>Longitude</dt><dd>${number(point.latlng[1],6)}°</dd></div><div><dt>Posisi terhadap boundary</dt><dd>${point.inside?'Di dalam boundary':'Di luar boundary'}</dd></div><div><dt>ID hole / target kedalaman</dt><dd class="mapPendingValue">Belum tersedia</dd></div></dl><p class="mapDetailNote">Progres DDR belum ditautkan ke lokasi ini.</p>`;
  el('mapClearSelection').onclick=clearSelection;
  updateLabels();
 }
 function clearSelection(){
  if(selected){const p=data.points.find(p=>p.id===selected);markers.get(selected).setIcon(icon(p));markers.get(selected).setZIndexOffset(0);}
  selected=null;el('mapSelectedPeek').classList.add('hidden');renderList();el('mapPointDetail').innerHTML='<span class="mapEyebrow">DETAIL LOKASI</span><h3>Pilih titik rencana</h3><p>Klik marker pada peta atau pilih dari daftar untuk melihat koordinat.</p><div class="mapEmptySymbol" aria-hidden="true">◎</div>';
 }
 function reset(){request++;map?.remove();map=null;boundary=null;pointsLayer=null;imagery=null;data=null;owner=null;selected=null;ready=false;markers.clear();el('mapSelectedPeek').classList.add('hidden');labels=false;plain=false;el('mapPointList').replaceChildren();el('mapSearch').value='';el('mapBoundaryToggle').checked=true;el('mapPointToggle').checked=true;el('mapLabelToggle').checked=false;el('mapWorkspace').classList.add('hidden');el('mapPointCount').textContent='—';el('mapArea').textContent='—';state('Menyiapkan peta…');el('mapPointDetail').innerHTML='<span class="mapEyebrow">DETAIL LOKASI</span><h3>Pilih titik rencana</h3><p>Klik marker pada peta atau pilih dari daftar untuk melihat koordinat.</p><div class="mapEmptySymbol" aria-hidden="true">◎</div>';}
 el('mapSelectedPeek').onclick=()=>el('mapPointDetail').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});
 el('mapFitBoundary').onclick=()=>fitBoundary();el('mapFitPoints').onclick=fitPoints;
 el('mapSatellite').onclick=()=>setBasemap(false);el('mapPlain').onclick=()=>setBasemap(true);
 el('mapSearch').addEventListener('input',renderList);
 el('mapBoundaryToggle').onchange=e=>{if(map)e.target.checked?boundary.addTo(map):map.removeLayer(boundary)};
 el('mapPointToggle').onchange=e=>{if(map)e.target.checked?pointsLayer.addTo(map):map.removeLayer(pointsLayer)};
 el('mapLabelToggle').onchange=e=>{labels=e.target.checked;if(map)updateLabels()};
 window.addEventListener('offline',()=>{if(map)setBasemap(true)});
 const baseSession=window.applySession;
 window.applySession=s=>{if(owner!==s.username)reset();baseSession(s);prime(s.username);};
 window.DrillingMap={show,reset};
})();
