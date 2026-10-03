/* Optional camera scanner. Keyboard scanners and manual entry use the same lookup. */
(() => {
  let stream=null,timer=null,epoch=0;
  function stop(){
    ++epoch;
    if(timer){clearTimeout(timer);timer=null}
    if(stream){stream.getTracks().forEach(t=>t.stop());stream=null}
    const video=document.querySelector('#cameraPreview');
    if(video){video.srcObject=null;video.classList.add('hidden')}
    document.querySelector('#startCamera')?.classList.remove('hidden');
    document.querySelector('#stopCamera')?.classList.add('hidden');
  }
  window.stopDrillingScanner=stop;
  const message=s=>{const el=document.querySelector('#cameraMessage');if(el)el.textContent=s};
  document.addEventListener('click',async e=>{
    if(e.target.id==='stopCamera'){stop();message('Kamera berhenti.');return}
    if(e.target.id!=='startCamera')return;
    stop();const active=epoch;
    if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.BarcodeDetector){message('Kamera tidak tersedia pada browser/koneksi ini. Gunakan scanner keyboard atau masukkan kode.');return}
    try{
      const supported=await BarcodeDetector.getSupportedFormats();
      if(active!==epoch||!document.querySelector('#trackingScanForm'))return;
      if(!supported.includes('qr_code')){message('Pembaca QR kamera tidak didukung browser ini. Gunakan scanner keyboard.');return}
      const detector=new BarcodeDetector({formats:['qr_code']});
      stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
      if(active!==epoch||!document.querySelector('#trackingScanForm')){stop();return}
      const video=document.querySelector('#cameraPreview');video.srcObject=stream;video.classList.remove('hidden');await video.play();
      if(active!==epoch){stop();return}
      document.querySelector('#startCamera')?.classList.add('hidden');
      document.querySelector('#stopCamera')?.classList.remove('hidden');
      message('Arahkan kamera ke QR core box atau sample.');
      const scan=async()=>{
        if(active!==epoch)return;
        try{
          const codes=await detector.detect(video);
          if(active!==epoch)return;
          const value=codes.find(x=>x.rawValue)?.rawValue;
          if(value){stop();const input=document.querySelector('#trackingCode');if(input){input.value=value;document.querySelector('#trackingScanForm').requestSubmit()}return}
        }catch(err){if(active!==epoch)return;message('Kamera gagal membaca QR: '+err.message)}
        timer=setTimeout(scan,350);
      };scan();
    }catch(err){stop();message('Kamera tidak bisa dibuka: '+err.message+'. Gunakan input manual atau scanner keyboard.')}
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop()});
  window.addEventListener('pagehide',stop);
  document.addEventListener('click',e=>{if(e.target.closest('[data-view],[data-go],[data-tab]')&&stream)stop()});
})();
