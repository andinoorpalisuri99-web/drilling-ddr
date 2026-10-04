MMS DRILLING v0.8.23 — RINGKASAN MANAGEMENT & PEMBARUAN APLIKASI
PAKET TANPA DATABASE. Upgrade kode v0.8.22.

INSTALASI LOKAL
Backup folder terlebih dahulu. Hentikan aplikasi (Ctrl+C), salin isi Drilling dari ZIP ke folder aplikasi yang sedang dipakai, replace file kode, lalu jalankan MULAI.bat.
Database dan file WAL/SHM tidak ada dalam ZIP ini; pertahankan data milik Anda.
Jangan clear site data/browser storage agar antrean offline tetap tersedia.

HOSTING/RENDER
Commit/push file kode beserta folder static ke repo yang dipakai layanan yang sama. Pastikan proses deploy berhasil dan layanan baru sudah berjalan. Pertahankan DRILLING_DB/volume database persisten serta konfigurasi hosting yang sudah dipakai.
Paket ini tidak melakukan deploy ke website publik. Mengunggah ZIP ke repo tanpa mengekstrak dan memperbarui file kode tidak memperbarui aplikasi.

PERUBAHAN PA/UA
Tampilan utama dan rincian rig memakai satu angka:
PA = (jam terjadwal - maintenance tercatat) / jam terjadwal x 100%.
UA = operating tercatat / (jam terjadwal - maintenance tercatat) x 100%.
Jam terjadwal tetap 10 jam per rig/tanggal yang memiliki DDR aktif non-Rejected, termasuk beberapa DDR pada tanggal yang sama. Tidak memakai jam tercatat sebagai pengganti denominator scheduled.
Jika jam kurang/belum terklasifikasi, angka berlabel Sementara. PA bisa lebih tinggi dan UA bisa lebih rendah dibanding angka akhir. Tidak ada aktivitas tambahan yang dimasukkan untuk mengisi jam kosong.
Angka dihitung ulang setelah revisi tersimpan dan Overview dimuat, atau pemeriksaan otomatis online 30 detik saat tab aktif/dialog tertutup.
Overlap, di luar jadwal, atau rincian tidak valid tetap menahan angka. UA — bila available=0. Tanggal tanpa DDR belum termasuk cakupan jadwal.

TAMPILAN
Ringkasan PA/UA lebih singkat; rincian jam dan rumus ada pada Rincian per rig & dasar hitung.
Catatan cakupan Overview, penjelasan komersial, panduan panjang pada menu operasional dan peta dipindahkan ke disclosure Panduan/Cakupan data.
Peringatan jam kurang, validasi, notifikasi offline, dan petunjuk penting input tetap tersedia. Data dan akses pengguna dipertahankan.

PERBAIKAN UPDATE
Penyebab yang ditemukan: HTML baru dapat menggunakan JavaScript lama dari cache service worker. Pemeriksaan versi sebelumnya langsung menganggap server lama masih berjalan, padahal halaman/browser yang tertinggal.
File JS/CSS kini memakai penanda versi pada URL. Saat online service worker memuat aset terbaru dari jaringan; saat offline memakai cache. API tetap tidak disimpan dalam cache tersebut.
Perbedaan versi mencoba penyelarasan otomatis sekali per pasangan versi/tab. Jika tetap berbeda, tampil versi halaman/server, informasi deploy belum sinkron, dan tombol Periksa pembaruan. Tidak ada reload loop.
Login tetap halaman awal. Sesi valid dapat dilanjutkan tanpa password. Tidak menghapus IndexedDB, database, sesi, maupun antrean offline untuk memperbaiki cache.
Pada perpindahan dari versi sebelum v0.8.23, bila tab yang sudah lama terbuka belum berubah, muat ulang setelah deploy selesai. Ctrl+F5 hanya diperlukan bila peramban masih menahan halaman lama. Pada server yang memang belum menjalankan kode terbaru, deploy/restart layanan tetap diperlukan.

HASIL UJI
- Migrasi nyata browser dengan cache/service worker v0.8.22 menuju server v0.8.23: login baru berhasil, antrean offline tetap ada.
- Versi server berbeda sengaja disimulasikan: satu penyelarasan otomatis lalu pesan informatif; tidak ada loop.
- Satu angka PA/UA seluruh dataset: 98,75% / 30,90% (Sementara), berdasarkan 42 DDR baseline. Angka di website dapat berbeda sesuai data/filter yang dipakai.
- 10 nav/10 subtab, 8 ukuran 320–1920, populated tables/form/QR/map: tidak ada overflow halaman/input atau error JavaScript pada skenario uji.
- Login awal, lanjut sesi, logout, jaringan lambat dan offline tersimpan lolos.
- Modul produksi, recovery, billing, downtime, sumber jam PA/UA, ekspor, validasi, auth dan database byte-identical terhadap v0.8.22. Perubahan PA/UA ada pada pemilihan nilai presentasi, bukan rawdata.
