# EPG Merger

Menggabungkan banyak file XMLTV lokal dan URL EPG eksternal menjadi satu `docs/epg.xml`.

## Struktur

- `data/sources.txt` → daftar URL EPG, satu URL per baris.
- `data/epg/` → file EPG lokal `.xml` atau `.xml.gz`.
- `scripts/merge_epg.py` → mesin penggabungan.
- `docs/epg.xml` → hasil akhir yang dipublikasikan GitHub Pages.
- `reports/epg-report.txt` → laporan sumber berhasil/gagal.
- `.github/workflows/build-epg.yml` → build otomatis dan deploy Pages.

## Cara memakai

1. Buat repository baru, misalnya `epg`.
2. Upload seluruh isi repository ini ke branch `main`.
3. Isi `data/sources.txt` dengan URL EPG Anda.
4. Masukkan EPG lokal ke `data/epg/`.
5. Jalankan workflow **Build EPG** secara manual sekali dari tab Actions.
6. Aktifkan GitHub Pages dengan **Source: GitHub Actions** jika belum aktif.

URL hasil:

`https://USERNAME.github.io/epg/epg.xml`

## Catatan

- Format yang ditargetkan adalah XMLTV (`<tv>`, `<channel>`, `<programme>`).
- URL `.xml` dan `.xml.gz` didukung.
- Jika satu sumber gagal, sumber lain tetap diproses.
- Channel duplikat berdasarkan `channel id` digabung.
- Programme duplikat berdasarkan channel, waktu, judul, dan deskripsi dihilangkan.
- Workflow berjalan setiap 6 jam dan juga dapat dijalankan manual.
