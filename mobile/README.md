# APK Android — CMS Kolaborasi (satu APK, multi perusahaan)

Pembungkus WebView utk aplikasi web CMS. **Satu APK dipakai SEMUA perusahaan**: tiap perusahaan punya
stack Docker/server sendiri (lihat `scripts/add-tenant.sh`); saat pertama dibuka, pengguna memasukkan
**kode perusahaan** (slug tenant → `https://<kode>.<BASE_DOMAIN>`) atau **URL lengkap** (termasuk
`http://IP:8879` utk LAN/VPN). Pilihan tersimpan — pengguna perusahaan A selalu masuk ke server A,
tak pernah menyentuh server B. Ganti perusahaan: **tekan-tahan ikon aplikasi → "Ganti Perusahaan"**.

## Build (di PC dengan Android Studio)
1. Buka folder `mobile/` di Android Studio (File → Open) — Gradle sync otomatis.
2. Sesuaikan `BASE_DOMAIN` di `TenantActivity.kt` dgn domain induk tenant-mu.
3. Build → Build APK(s) → `app/build/outputs/apk/`. Utk rilis Play Store: buat keystore sendiri
   (ganti `signingConfig` di `app/build.gradle`) dan set `usesCleartextTraffic=false` bila semua
   tenant sudah HTTPS.

## Yang sudah ditangani wrapper
- Cookie sesi persisten (login awet), localStorage (draft blok), SSE realtime.
- Unggah berkas/gambar (file chooser galeri/kamera), unduh ekspor DOCX (DownloadManager + cookie).
- Pull-to-refresh, tombol back = mundur riwayat web, link eksternal dibuka di browser.
- `usesCleartextTraffic=true` default: supaya `http://IP:8879` (LAN/VPN) jalan — ketatkan utk produksi.
