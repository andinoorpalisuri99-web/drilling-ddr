MMS DRILLING v0.8.21 — PA/UA & MOVING PROGRESS
Paket lengkap BERISI DATABASE revisi kiriman terakhir: 42 DDR, sampai 3 Oktober 2026.

CARA PAKAI
1. Hentikan aplikasi lama (Ctrl+C) dan backup seluruh foldernya.
2. Ekstrak ZIP ini ke FOLDER BARU. Jalankan Drilling/MULAI.bat dari folder hasil ekstraksi.
3. Login memakai akun/password sebelumnya. Sesi lama dikosongkan; akun dan password tidak diganti.
4. Jangan menimpa database yang sudah menerima input tambahan setelah RAR terakhir dikirim. Bila ada input lebih baru, database terbaru perlu digabung dahulu.
5. Jangan hapus data browser / antrean offline. Data yang belum tersinkron di perangkat tidak ada dalam ZIP ini.
6. Jika tampilan masih versi lama, muat ulang Ctrl+F5 setelah server baru berjalan. Pertahankan alamat/port yang sama untuk mengakses antrean offline browser lama.

PERUBAHAN
- Overview PA dan UA per rig serta gabungan, mengikuti filter periode/rig aktif.
- Rincian per rig dapat dibuka; klik rig untuk memfilter Overview.
- Notifikasi ringkas kelengkapan jam mencakup semua tanggal rig terpilih, termasuk di luar filter periode. Buka untuk melihat tanggal, kekurangan menit, interval kosong, serta tombol Buka DDR.
- Revisi oleh admin tetap mengikuti alur koreksi dan audit yang sudah ada. Perhitungan diperbarui setelah simpan/muat Overview; jika Overview terbuka online, pemeriksaan otomatis setiap 30 detik (selama tab aktif dan dialog tertutup).
- Jam kurang tidak menghentikan pekerjaan pada rilis ini. Tidak ada aktivitas fiktif untuk menutup selisih.
- Moving Distance diganti input Moving Progress (%), 0–100: persentase penyelesaian perpindahan menuju tujuan pada DDR tersebut. Bukan persentase jam dan tidak dijumlahkan sebagai produksi. Tidak ada konversi meter menjadi persen.
- Jarak historis tetap disimpan dan ditampilkan sebagai catatan saat koreksi. Form lama tanpa progress tetap menampilkan jarak aslinya; form baru/yang direvisi memakai Progress (%). PDF/Excel menyertakan data riwayat pada lampiran.
- Urutan aktivitas TIME pada detail PDF dan ekspor PDF/Excel mengikuti jam mulai DDR, termasuk saat melewati tengah malam. Raw data tidak diurutkan ulang/disunting.

DASAR PA/UA
Jadwal proyek: 07:00–17:00 (10 jam per rig per tanggal, termasuk istirahat).
Beberapa DDR/hole/shift pada rig dan tanggal sama dihitung sebagai SATU hari-rig.
Cakupan: tanggal dengan DDR non-Rejected untuk rig aktif. Tanggal tanpa DDR tidak otomatis diasumsikan bekerja. PA/UA ini bukan cakupan kalender penuh atau uptime 24 jam.
Operating: OH/coring + kelompok aktivitas pendukung, termasuk Geophysical Logging.
Non-operating: Moving/setup, Travelling, standby/cuaca, P2H, briefing, safety meeting, istirahat.
Maintenance: Breakdown, Repair & Maintenance, Maintenance saja.
PA = Available / Scheduled x 100%; UA = Operating / Available x 100%.
Fleet memakai jumlah jam seluruh rig, bukan rata-rata persentase rig.
Acuan definisi: GMG Time Classification Framework (2020), Table 3:
https://gmggroup.org/wp-content/uploads/2024/07/20200713_Time_Classification_Framework-GMG-DAU-v01-r01-1.pdf
Pengelompokan aktivitas dan jadwal 10 jam mengikuti kebijakan proyek yang disepakati. Ini bukan klaim sertifikasi.

JAM BELUM LENGKAP
S=scheduled, D=maintenance tercatat, O=operating tercatat, U=jam kosong/belum terklasifikasi.
PA sementara: (S-D-U)/S sampai (S-D)/S.
UA sementara: O/(S-D) sampai (O+U)/(S-D), jika penyebut >0.
Rentang mencerminkan kemungkinan klasifikasi jam yang belum diketahui. Data tidak diisi otomatis sebagai standby/maintenance.
Setelah semua jam terklasifikasi, batas rentang menjadi satu angka.
Jika ada overlap, jam di luar jadwal, atau rincian tidak valid, angka PA/UA terkait ditahan (—) sampai direvisi. UA juga — jika available=0.
PA/UA menyeluruh hanya tampil pada role pengelola; teknisi tetap melihat DDR miliknya, tanpa bocoran data pengguna lain.

DATA YANG TETAP PERLU REVISI
DR-03 / 21 September 2026 / DDR #6: 9 jam 45 menit, kosong 15:45–16:00.
MMS-02 / 2 Oktober 2026 / DDR #42: 9 jam, kosong 12:00–13:00.
Dua kekurangan ini sengaja dipertahankan sesuai sumber. Revisi uji hanya dilakukan pada salinan QA, tidak masuk paket.

VERIFIKASI RILIS
42 DDR, tidak ada duplikat identitas rig/tanggal/shift/hole atau client_request_id.
Semua tabel sumber terakhir dipertahankan persis, kecuali sessions dikosongkan.
SQLite integrity_check=ok; foreign_key_check bersih.
Total meter aktif non-Rejected tetap 537,15 m; breakdown/perawatan tetap 270 menit.
36 hari-rig, 34 lengkap, kekurangan 75 menit. Filter semua data: PA 98,40–98,75%; UA 30,90–31,25% sementara.
Uji: koreksi asli via API pada salinan database menghilangkan notifikasi dan mengubah angka menjadi pasti tanpa mengubah meter/downtime; agregasi lintas DDR/shift, penjumlahan jam fleet, nol available, overlap, di luar jadwal, inactive/rejected, role privacy, validasi persentase, preservasi jarak historis, antrean offline, ekspor PDF/XLSX, viewport 320/390/768/1440 dan regresi zoom grafik.
