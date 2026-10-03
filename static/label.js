const qr=document.getElementById('labelQR'),button=document.getElementById('printLabel'),status=document.getElementById('printStatus');
qr.addEventListener('load',()=>{button.disabled=false;status.textContent='QR siap dicetak. Pastikan ukuran kertas label sesuai printer.'});
qr.addEventListener('error',()=>{status.textContent='QR gagal dimuat. Periksa sesi login dan instalasi reportlab.'});
button.addEventListener('click',()=>window.print());
if(qr.complete){if(qr.naturalWidth)qr.dispatchEvent(new Event('load'));else qr.dispatchEvent(new Event('error'))}
