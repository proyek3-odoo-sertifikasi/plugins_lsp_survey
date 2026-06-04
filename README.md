# LSP Survey Extension

Module addon Odoo ini dikembangkan untuk memperluas modul bawaan `survey` guna mendukung alur kerja sertifikasi kompetensi pada Lembaga Sertifikasi Profesi (LSP). Modul ini mengimplementasikan hak akses ketat antara **LSP Asesor** dan **LSP Admin**, serta memetakan konsep *Section* pada survey menjadi **Unit Kompetensi** lengkap dengan **Kode Unit**.

---

## Fitur Utama

### 1. Alur Validasi Soal (LSP Workflow State)
Setiap pertanyaan (*question*) dan bagian (*section*) memiliki siklus hidup validasi sebagai berikut:
- **Draft**: Status awal saat soal baru dibuat oleh Asesor.
- **Waiting**: Diajukan oleh Asesor untuk divalidasi oleh Admin.
- **Revise**: Dikembalikan oleh Admin ke Asesor untuk diperbaiki (dengan Catatan Admin).
- **Active**: Disetujui oleh Admin. **Hanya soal berstatus Active yang akan muncul pada tampilan ujian peserta.**

### 2. Manajemen Peran & Hak Akses Ketat
Modul memisahkan tanggung jawab kerja secara ketat menggunakan grup keamanan Odoo:
*   **LSP Asesor** (`lsp_survey.group_lsp_asesor`):
    *   Satu-satunya peran yang diperbolehkan membuat (*create*) soal dan section baru.
    *   Dapat mengedit soal berstatus *Draft* dan *Revise*.
    *   Dapat mengajukan validasi (*action_submit*).
    *   *Tidak bisa menyetujui (approve) atau meminta revisi soal sendiri.*
*   **LSP Admin** (`lsp_survey.group_lsp_admin`):
    *   Dapat melihat daftar soal yang diajukan.
    *   Dapat menyetujui (*action_approve*) untuk mengaktifkan soal.
    *   Dapat meminta revisi (*action_revise*) dengan mengisi kolom catatan admin.
    *   *Dilarang keras membuat soal baru (hak eksklusif Asesor).*

### 3. Representasi Unit Kompetensi (Section)
Setiap *Section* di dalam lembar ujian mewakili satu **Unit Kompetensi** yang memiliki dua data utama:
*   **Nama Unit**: Menggunakan field bawaan Odoo (`title`) yang dilabeli ulang secara kontekstual menjadi **Nama Unit / Pertanyaan**.
*   **Kode Unit**: Field tambahan baru (`unit_code`) untuk mencatat nomor kode standardisasi kompetensi (contoh: `TIK.PR01.001.01`).

### 4. Tampilan Frontend yang Dinamis & Aman
*   **Kode Unit Kompetensi**: Ditampilkan secara otomatis tepat di bawah nama unit kompetensi (dengan gaya teks kecil/muted) pada halaman ujian peserta.
*   **Keamanan Navigasi (Anti-Crash)**: Override internal pada logika perutean halaman survey untuk mencegah error `ValueError: False is not in list` ketika peserta menavigasi halaman yang berisi soal belum aktif atau kosong.

---

## Struktur Direktori

```text
lsp_survey/
├── __init__.py
├── __manifest__.py
├── README.md                  # Dokumentasi modul (file ini)
├── models/
│   ├── __init__.py
│   └── survey_question_inherit.py   # Logika workflow, filter active, & validasi
├── security/
│   ├── ir.model.access.csv    # Hak akses model
│   └── lsp_security.xml       # Definisi grup LSP Admin & LSP Asesor
└── views/
    ├── survey_question_views_inherit.xml   # Penyesuaian form, list, & kolom di backend
    └── survey_templates_inherit.xml       # Kustomisasi tampilan halaman ujian frontend
```

---

## Cara Instalasi / Pembaruan

1. Letakkan folder `lsp_survey` ini di dalam direktori `addons` Odoo Anda.
2. Perbarui daftar modul Odoo (*Update Apps List*) di menu Pengaturan developer.
3. Cari modul dengan nama **LSP Survey Extension** (`lsp_survey`).
4. Klik **Install** atau **Upgrade**.
5. Jika menggunakan Docker, Anda juga dapat memicu pembaruan lewat terminal:
   ```bash
   docker compose exec odoo-web odoo -u lsp_survey -d <nama_database> --stop-after-init
   ```

---

## Catatan Pengujian
- Saat menguji survey sebagai peserta, pastikan Anda telah menyetujui setidaknya satu soal di dalam setiap section agar ujian tidak terdeteksi kosong (*void*).
- Status aktif/tidaknya suatu section (Unit Kompetensi) diatur secara otomatis: Section akan muncul di halaman peserta jika dan hanya jika terdapat minimal **satu soal aktif** di bawah section tersebut.
