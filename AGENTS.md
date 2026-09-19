# warehouse_app — konteks & batasan

## Tujuan

Custom app Frappe/ERPNext untuk **org Gudang (barang jadi)**, berjalan di site yang sama dengan `production_app` (site `frontend`). Prinsip dasar (keputusan resmi user, 2026-09-20): **native ERPNext tidak boleh terpengaruh custom app mana pun** — production_app fokus user manufacturing, dan semua tooling gudang dikembangkan di app ini. Saling lepas: warehouse_app tidak boleh mengubah perilaku produksi, production_app tidak boleh memaksa perilaku native/gudang.

## Latar (kenapa app ini ada)

- 2026-09-19 (FU48, production_app): gudang sementara pakai Desk ERPNext native; SPA produksi dibersihkan jadi produksi-only.
- 2026-09-20 (FU57, production_app): user menemukan MR native terpaksa wajib Work Order akibat guard custom app, lalu memutuskan: *"native erpnext harusnya ga terpengaruh oleh custom app… nanti kita bikin custom app untuk gudang sendiri aja, yang ini fokus untuk user manufacturing aja"*. Guard dihapus (`retire_mr_guard()`), konsekuensi MR serah terima manual bisa "yatim" diterima user.
- Kesimpulan: **Desk native hanya jembatan**; app gudang terpisah ini adalah rumah permanen tooling gudang. Riwayat lengkap: memory `fu48-interim-gudang-desk` + ledger SDD production_app.

## Domain (dunia yang dioperasikan)

- Produksi roti/bakery, company abbr `-ROPI`; gudang terkait: Gudang Bahan Baku, Gudang Barang Jadi, Gudang Produksi.
- Alur serah terima produksi→gudang: produksi membuat Material Request Material Transfer per Work Order (Form Order = MR dengan `custom_is_form_order`), mengirim via Stock Entry Material Transfer; pelacakan per **batch** dan **box** (Box 1/Box 2 = Float kg); partial SE dari Desk dihitung terkirim penuh; over-request gagal atomik di SE.
- Role gudang: "Gudang Barang Jadi". Celah pre-existing (diparkir): role murni tak punya read Company → tambah Stock User bila perlu simpan dokumen.
- Endpoint server gudang di production_app (`create_request`/`cancel_request`/`fulfill_form_order`) sengaja dibiarkan hidup tanpa pemanggil SPA — reversibel, jangan dihapus tanpa keputusan user.

## Status (2026-09-20)

- W1 selesai: scaffold `bench new-app` + install di site `frontend`, kode tersinkron ke 6 container frappe. Belum ada doctype/API/UI.
- Operasi gudang saat ini masih lewat Desk native (interim) + SPA produksi hanya untuk produksi.

## Scope & pertanyaan terbuka (bahan planning)

Belum dikunci — putuskan bersama user di sesi planning (pakai SDD bila besar):
- Fitur inti gudang: terima serah terima, stok masuk/keluar/transfer, MR ke produksi, counting/opname, laporan stok, apa lagi.
- Bentuk UI: app berbasis Desk (doctype + workspace + client script) vs SPA kedua ala production_workspace.
- Apakah serah terima & alur MR gudang pindah ke sini (beserta endpoint dormant di production_app), atau tetap di produksi dan app ini melengkapi.
- Perbaikan role/perm gudang (Company read, delete draft MR sendiri) — habitat alami perbaikan ini app ini.

**Dilarang (berlaku balik juga ke sini):** edit core Frappe/ERPNext; memaksa dokumen native lewat field custom (jangan ulangi pola guard FU48a); mengubah alur produksi di production_app dari app ini.

## Lingkungan & deploy

- Frappe/ERPNext v16 di Docker compose `erpnext-new`: backend `erpnext-new-backend-1`, frontend `-frontend-1`, queue `-queue-short-1`/`-queue-long-1`, scheduler, websocket, db `-db-1` (root/admin, DB `_e9ef387b375d0575`); bench di `/home/frappe/frappe-bench`; satu-satunya site: `frontend`.
- HTTP CLI selalu `http://127.0.0.1:8081`; ada vite menyasar `[::1]:8081` — jangan dibunuh.
- **Pipeline deploy kode app ini** (folder `apps/` bukan bind mount):
  1. `bench --site frontend install-app warehouse_app` / migrate dari backend bila perlu.
  2. docker cp folder app + `chown -R frappe:frappe` ke **6 container** (backend, frontend, queue-short, queue-long, scheduler, websocket).
  3. Container non-backend juga butuh `warehouse_app.pth` + dist-info di `env/lib/python3.14/site-packages` (image-nya hanya pip-install frappe+erpnext) — salin dari backend.
  4. Volume `sites` shared antar container → `apps.txt`/install cukup sekali dari backend.
  5. Restart container terkait + `curl http://127.0.0.1:8081/api/method/ping`.
- Gejala dikenal: `ModuleNotFoundError` saat boot worker untuk app yang kodenya tidak ada di container itu (non-fatal, app di-skip). Sisa pre-existing yang memang belum diheal: `pos_next`, `bakery_manufacturing`, `email_delivery_service` absen di container queue.

## Protokol kerja

- Baca `TASKS.md` + `PROJECT_STATE.md` sebelum bekerja; penomoran tugas pakai prefiks `W#`.
- Tandai IN_PROGRESS di `PROJECT_STATE.md` sebelum edit; DONE butuh **bukti eksekusi** (jangan dari baca kode saja). Satu task aktif pada satu waktu.
- Residu fixture uji = 0 (hapus user/dokumen buatan + Sessions/Activity Log). Browser milik user — jangan pernah bertindak sebagai akun aslinya (ropierpnext@gmail.com); logout via fetch + `X-Frappe-CSRF-Token` sebelum login fixture.
- Commit di repo ini (branch `main`); push/merge hanya atas permintaan user. Rilis aset frontend mengikuti pola production_app bila suatu saat app ini punya SPA.
