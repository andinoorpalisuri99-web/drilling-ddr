MMS Drilling v0.8.20 — DATA GABUNGAN 3 OKTOBER 2026
Paket ini BERISI DATABASE hasil penggabungan, bukan patch tanpa database.

CARA PAKAI
1. Hentikan aplikasi dan backup seluruh folder yang sedang dipakai.
2. Ekstrak paket ini ke FOLDER BARU. Jalankan MULAI.bat di folder Drilling hasil ekstraksi. Login menggunakan akun/password sebelumnya.
3. Jangan menjalankan dua aplikasi pada port yang sama. Jangan menimpa database yang sudah menerima input lebih baru dari file kiriman ini. Bila ada input tambahan setelah pengiriman, database terbaru perlu digabung kembali.
4. Pertahankan data browser/antrean offline. Paket hanya mencakup data yang sudah tersimpan di database kiriman.

HASIL
Kode tetap v0.8.20 dengan perbaikan grafik zoom.
32 DDR lama dipertahankan, 7 DDR baru (#36–42) ditambahkan, 30 DDR lama menggunakan revisi terbaru dari kiriman, 2 DDR lama tetap sama. Total39.
Pembaruan approval, koreksi, billing, target dan audit terkait ikut dipertahankan. Semua tabel lama selain sesi tetap ada dalam database penerus; update laporan diverifikasi revision-nya meningkat dan identitas pengirimannya sama.
Duplikat rig/tanggal/shift/hole (trim+casefold):0. Duplikat client_request_id:0. Pemeriksaan integrity/foreignkey lolos.
Seluruh data sumber kiriman dipertahankan kecuali sesi login aktif; pengguna login ulang. Akun/hash password tidak berubah.
Total aktif non-Rejected seluruh tanggal526.30m = OH378.00 + Core148.30. Ditagih461.45 + Tidakditagih64.85. Maintenance255menit/4.25jam. Angka berdasarkan filter seluruh data; filter harian/bulanan dapat berbeda.

PA/UA belum ditambahkan: dasar scheduled hours dan operating hours perlu ditetapkan. Catatan jam tidak penuh tidak otomatis diisi standby. Lihat CATATAN-JAM.csv untuk perbandingan terhadap asumsi10jam per shift, bukan keputusan bahwa jam hilang pasti salah.

QA: database lineage/superset, unique keys, integritas, semua tabel sumber setara (kecuali sessions), hitung meter independen, browser39DDR/detailPDF42/billing20/overview526.3m. Kode aplikasi tidak berubah dari v0.8.20.
