MMS DRILLING v0.8.22 — LAYOUT, LOGIN FIRST & PROJECT ICON
PAKET KODE TANPA DATABASE. Upgrade dari v0.8.21.

PASANG DI KOMPUTER LOKAL
1. Hentikan aplikasi lama (Ctrl+C). Backup folder aplikasi/database terlebih dahulu.
2. Ekstrak ZIP ini. Salin isi folder Drilling ke folder aplikasi v0.8.21 yang sedang dipakai; replace file kode yang sama.
3. drilling.db, drilling.db-wal, drilling.db-shm dan folder backup tidak ada dalam paket ini. Jangan hapus atau mengganti database yang ada.
4. Jalankan MULAI.bat dari folder aplikasi tersebut. Muat ulang browser Ctrl+F5.
5. Pertahankan alamat/port browser dan data situs supaya antrean offline tetap tersedia. Jangan clear site data.

UNTUK WEBSITE/HOSTING
Deploy isi kode ke aplikasi/layanan yang sama melalui proses hosting Anda. Pertahankan konfigurasi DRILLING_DB dan volume database persisten. ZIP ini tidak mengubah konfigurasi hosting, tidak menyertakan database, dan belum dipasang otomatis ke website publik.

PERUBAHAN
- Konsistensi jarak, judul, pemisah, kartu, tabel, filter, tombol, form dan tampilan mobile pada seluruh nav.
- Ukuran kontrol dan fokus keyboard lebih jelas; scroll padding untuk header/footer tetap.
- Empty field hint tidak menyisakan ruang kosong berlebihan pada Input Shift.
- Keterangan Target dasar historis diperjelas agar tidak terkesan seluruh halaman target read-only.
- Login tampil sejak HTML pertama dimuat, termasuk saat jaringan lambat; workspace tidak tampil sebelum masuk.
- Bila sesi valid masih tersimpan, tersedia Lanjutkan sebagai [akun]. Tidak wajib mengetik password ulang. Saat sesi berakhir, login kembali.
- Mode offline tetap tersedia dari halaman login melalui tombol Masuk mode offline tersimpan, sesudah login online dengan Ingat saya dan cache master sudah tersedia. Antrean offline tidak dihapus.
- Favicon SVG + ICO khusus proyek: menara bor emas dan mata bor putih di atas latar gelap, mengikuti identitas warna aplikasi. Menggantikan ikon bumi default browser.

RUANG LINGKUP
Tidak mengubah rumus produksi, recovery, billing, downtime, PA/UA, validasi DDR, ekspor PDF/Excel, atau struktur database. Backend hanya penyesuaian versi dan penyajian favicon. Database di workspace uji tetap identik dengan v0.8.21; file database tidak ikut ZIP.

VERIFIKASI
10 nav: Overview, Target, Peta, Input Shift, Daily report, Equipment, Sample, Cost, Master Rig, Pengguna.
10 subtab operasional: equipment/material/stock, boxes/samples/custody/tracking, programs/expenses/invoices.
Viewport 320,390,768,844,961,1024,1440,1920; tabel berisi data, form tambah, edit rig, QR tracking, peta. Tidak ada overflow halaman/input atau error JavaScript dalam skenario ini.
Login fresh, reload dengan sesi valid, lanjut sesi tanpa password, logout/reload, offline tersimpan, jaringan lambat, endpoint favicon SVG/ICO diuji pada salinan database.

ACUAN DESAIN
IBM Carbon: tabel, jarak kolom dan susunan data.
https://www.carbondesignsystem.com/building-blocks/core/components/data-table/specifications
Microsoft Fluent 2: grid, spacing dan konsistensi hubungan komponen.
https://fluent2.microsoft.design/layout
Google Material 3: layout adaptif dan hierarki.
https://m3.material.io/foundations/layout/canonical-examples/overview
W3C WCAG 2.2: fokus keyboard tidak tertutup header/footer.
https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum
Referensi diterapkan sesuai kebutuhan aplikasi. Bukan klaim sertifikasi WCAG atau standar perusahaan tertentu; hasil verifikasi terbatas pada skenario dan perangkat uji di atas.
