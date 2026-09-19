# PLANNING_PROMPT.md — tempel ke sesi baru di folder warehouse_app

> Cara pakai: buka sesi ZCode baru di `/Users/rotiropi/erpnext-new/apps/warehouse_app`, tempel blok di bawah.

---

Kamu mulai sesi **planning fitur pertama warehouse_app** (custom app Frappe/ERPNext v16 untuk org Gudang barang jadi). Ini sesi PLANNING ONLY — jangan implementasi apa pun.

## 1. Baca dulu (wajib, sebelum apa pun)

- `AGENTS.md` — tujuan project, latar keputusan FU48/FU57, domain, lingkungan & deploy, protokol kerja, larangan permanen.
- `TASKS.md` + `PROJECT_STATE.md` — status: W1 (scaffold + install) selesai, belum ada doctype/API/UI.

## 2. Kumpulkan keputusan scope sebelum mendesain

Di `AGENTS.md` ada daftar "Scope & pertanyaan terbuka" (bentuk UI, fitur inti, pindah/pisah alur serah terima, perbaikan role/perm). Untuk setiap keputusan yang mengubah arah desain, pakai `AskUserQuestion` — **selalu taruh rekomendasimu sebagai opsi pertama berlabel "(Direkomendasikan)"**. Pertanyaan yang kututup tanpa dijawab artinya: pakai rekomendasimu. Jangan menggantung keputusan; jangan tanya hal yang bisa kamu putuskan sendiri dari konteks.

## 3. Verifikasi behavior native di source, jangan dari ingatan

Sebelum mendesain doctype/alur, verifikasi perilaku ERPNext v16 yang terpasang di container (`docker exec erpnext-new-backend-1`, source di `/home/frappe/frappe-bench/apps/{frappe,erpnext}`) untuk apa pun yang kamu andalkan: Stock Entry, Material Request, Stock Reconciliation, Batch, bin/SL Entry, role & permission, dsb. Catat temuan verbatim (file + baris) di plan. Juga inventarisasi apa yang sudah ada di production_app (alur serah terima, endpoint gudang dormant `create_request`/`cancel_request`/`fulfill_form_order`, role Gudang Barang Jadi) supaya tidak dirancang dobel.

## 4. Tulis plan mengikuti pola production_app

- `IMPLEMENTATION_PLAN.md` — requirements vs desain, fase dengan gate + acceptance criteria yang bisa diverifikasi lewat eksekusi (bukan baca kode), bagian "yang sengaja TIDAK berubah".
- Pecah ke `TASKS.md` sebagai entri `W#` berurutan (satu entri = satu unit se-commit); tandai dependency antar task.
- Update `PROJECT_STATE.md`. Gaya tulisan padat — tanpa teks filler.

## 5. Subagent yang wajib kamu pakai

- **Riset paralel (`general-purpose` atau `Explore`, dijalankan berbarengan)**: (a) riset source ERPNext v16 untuk doctype/method kunci; (b) inventaris production_app (repo + git history + ledger `.superpowers/sdd/`) untuk alur & endpoint yang sudah hidup. Kembalikan kesimpulan + path/bukti, bukan dump file.
- **`advisor`**: minta pendapat kedua untuk setiap keputusan arsitektur utama (bentuk UI, penempatan alur serah terima, strategi permission gudang, pemisahan data vs production_app). Masukkan hasilnya sebagai bagian "Rulings" di IMPLEMENTATION_PLAN.md.
- Saat implementasi NANTI (sesi lain): implementer `general-purpose` per task (working tree, tidak commit), `code-reviewer` sebelum tiap commit, walkthrough UI dijalankan di sesi utama lewat browser.

## 6. Batasan keras (ringkas; lengkapnya di AGENTS.md)

Tanpa edit core Frappe/ERPNext. Tanpa memaksa dokumen native lewat field custom (jangan ulangi guard FU48a). Jangan ubah alur produksi di production_app. Residu fixture = 0. Commit di repo ini, **tanpa push**.

## Deliverable akhir sesi ini

`IMPLEMENTATION_PLAN.md` baru + `TASKS.md`/`PROJECT_STATE.md` ter-update + Rulings advisor tercatat + satu commit di `main`. Laporan penutup: keputusan yang sudah terkunci, keputusan yang masih menunggu saya, dan task `W#` pertama yang dependency-ready.
