# TASKS — warehouse_app

Custom app untuk org gudang (finished-goods warehouse). Keputusan FU57 (production_app, 2026-09-20): native ERPNext harus bebas dari pengaruh custom app manufacturing; production_app fokus user manufacturing; tooling gudang = app terpisah ini.

Planning fitur pertama: lihat `IMPLEMENTATION_PLAN.md` (keputusan user 2026-09-20 + rulings advisor R1-R10). Eksekusi per entri di bawah; satu entri = satu commit; DONE butuh bukti eksekusi.

## W1 — Scaffold + install di site frontend — DONE (2026-09-20)
- `bench new-app warehouse_app` di container backend (title "Warehouse App", license mit), lalu `bench --site frontend install-app warehouse_app` (site yang sama dengan production_app).
- Kode host = repo ini. Sinkron ke container via docker cp (folder `apps/` bukan bind mount) ke 6 container frappe: backend, frontend, queue-short, queue-long, scheduler, websocket + chown frappe:frappe.
- 4 container non-backend (queue×2, scheduler, websocket) juga perlu `production_app.pth` + `warehouse_app.pth` + dist-info di `env/lib/python3.14/site-packages` (image hanya pernah pip-install frappe+erpnext) — disalin dari backend.
- Bukti: `bench --site frontend list-apps` → warehouse_app 0.0.1 tercantum; `frappe.get_installed_apps` terbaca dari scheduler; `import warehouse_app` OK dari python worker queue (queue-short) versi 0.0.1; `ping` → pong; home 200.
- Heal utang lama (side effect W1): container queue/scheduler/websocket tidak pernah punya kode `production_app` (ModuleNotFoundError tiap boot worker sejak image dibangun). Kode + .pth production_app kini disalin ke 4 container itu. Sisa pre-existing, tidak diketuk: `pos_next`, `bakery_manufacturing`, `email_delivery_service` juga tidak ada di container queue (error non-fatal, worker tetap jalan).

## W2 — Verifikasi pradesain (Fase A) — DONE (2026-09-20)
Bukti eksekusi (docker exec / grep pada source terpasang), tercatat verbatim di `IMPLEMENTATION_PLAN.md` §4:
- `@frappe.whitelist()` di mapper `make_stock_entry` — `material_request.py:935-936`; qty = sisa pending; `batch_no` tidak ter-map.
- Over-qty ditolak atomik saat SE submit — `material_request.py:424-429`; MR "Transferred" saat `per_ordered==100` — `status_updater.py:125-127`; hook update — `erpnext/hooks.py:358-359`.
- Replacement trap Custom DocPerm — `frappe/permissions.py:512`; Workspace v16 punya `roles` — `frappe/desk/doctype/workspace/workspace.json`.
- Audit mirror production_app (R8): `handover.py:735-777` fail-safe, hanya `db.set_value("Work Order", …)` (`:723,:1249`) — field tracking native MR/SE tidak disentuh.

## W3 — Script Report "Serah Terima Gudang" (Fase B) — PENDING
Depends: W2. Files & desain: `IMPLEMENTATION_PLAN.md` §5 Fase B (grain MR Item, filter arah gudang, bucket `per_ordered`, qty-only, roles Gudang Barang Jadi + Stock Manager; butuh `__init__.py` folder modul `warehouse_app/warehouse_app/warehouse_app/` yang kini kosong).
Gate: migrate sukses; query via API sebagai fixture user role gudang; 3 kasus derivasi benar (belum/sebagian/terkirim) atas data uji yang lalu dibersihkan; user tanpa role ditolak.

## W4 — Aksi buat SE dari papan (Fase C) — PENDING
Depends: W3. `serah_terima_gudang.js`: chip status + tombol "Buat Stock Entry" → `frappe.model.open_mapped_doc` ke mapper native; fallback kolom link MR (2 klik) bila tombol in-report rapuh — putusan dicatat di bukti.
Gate: SE draft berisi sisa; submit native sukses; over-qty ditolak native; bucket papan berganti; nol endpoint baru.

## W5 — Workspace "Warehouse App" (Fase D) — PENDING
Depends: W3. `…/warehouse_app/workspace/gudang/gudang.json`: public + roles [Gudang Barang Jadi], shortcut report + list MR/SE + Stock Balance; content header sederhana.
Gate: workspace terlihat role gudang & System Manager, tak terlihat user lain (cek API desktop); tersinkron 6 container (pipeline deploy AGENTS.md).

## W6 — E2E walkthrough + residu 0 + guard perm (Fase E) — DONE (2026-09-20)
- Walkthrough browser end-to-end sebagai fixture user `zztest-w6@example.com` (Gudang Barang Jadi + Stock User, bukan akun asli): login → nav "Gudang" tampil → workspace "Gudang — Papan Serah Terima" (4 shortcut) → papan "Serah Terima Gudang" render data nyata produksi + fixture (chip Belum Dikirim/Sebagian/Terkirim, kolom WO & Box display-only, tanpa valuasi) → tombol "Buat Stock Entry" membuka SE draf via mapper native (Material Transfer, qty=sisa, gudang benar) → Save+Submit `MAT-STE-2026-07047` sukses → papan otomatis pindah bucket "Terkirim" & tombol hilang. Bukti screenshot: `/tmp/w6-screens/`.
- Temuan & perbaikan (commit `a070259`, hasil review independen + verifikasi eksekusi):
  1. Nav atas /desk dirender dari **Desktop Icon → Workspace Sidebar** — tanpa keduanya grup "Gudang" tidak muncul walau workspace diizinkan (`boot.workspace_sidebar_item` memuat, tapi render butuh ikon). Fix: json `workspace_sidebar/gudang/gudang.json` + `upgrade.py` idempoten (`ensure_workspace_sidebar` + `ensure_desktop_icon`, after_install/after_migrate) — pola `production_app.upgrade.ensure_desktop_icon`.
  2. Default filter Link harus nama eksak: "Gudang Barang Jadi" ditolak client ("Warehouse … not found"); diganti "Gudang Barang Jadi - ROPI" (`resolve_warehouse` tetap menerima bentuk tanpa abbr).
  3. Guard residu buta terhadap Item bernama auto (site memakai Item naming series — name/item_code dioverride; ITEM00248 "ZZTEST W3 Gate Item" lolos guard lama). Fix: hitung/sweep juga via `item_name` (prefix + varian spasi).
  4. File stray package-level `workspace_sidebar/gudang.json` (drift di container; AppleDouble dari docker cp macOS bisa menggugurkan migrate) dihapus dari 6 container; pipeline sync kini menyertakan pembersihan `._*`.
- Guard final pasca-teardown `ok: true` — residu ZZTEST-W semuanya 0; Custom DocPerm Company = 12 baris baseline identik (nol dari warehouse_app); Stock User read Company = 1. 6 container sinkron + restart + ping pong.
- Catatan rough edge native (pre-existing, tidak memblokir, tidak di-fix di sini): toast "No permission for Stock Settings" saat user non-admin membuka form Stock Entry di Desk.

## W7 — Company read utk Gudang Barang Jadi — DITUTUP (2026-09-20, keputusan user)
User memutuskan: **user gudang dipasangkan role `Stock User`** (SOP, nol kode — Stock User memang punya read Company, `company.json:1078-1080`). Tidak akan dieksekusi sebagai kode; entri disimpan untuk riwayat. Bila kelak kebijakan berubah ke single-role, desain fallback (`frappe.permissions.add_permission` additive-only) tetap ada di `IMPLEMENTATION_PLAN.md` §7.

## W8 — Smoke test endpoint dormant production_app (PARKIR, non-W2)
Trigger: kapan pun setelah W6. Panggil `create_request`/`cancel_request`/`fulfill_form_order` (production_app) dengan fixture, pastikan tak membusuk, bersihkan residu.

## W9 — Request serah terima ala-gudang (adonan ke + item) — DONE (2026-09-20)
Depends: fitur pertama live (W3–W6). Keputusan user: gudang butuh bikin request per kanban/WO dalam bahasa mereka (adonan ke + nama item), bukan nomor WO + qty; implementasi hanya di warehouse_app, tanpa sentuh core/native. Ruling advisor **R11** (Opsi A): UI tipis (Page `gudang_request`: daftar WO "Adonan {ke} — {item}" + dialog Box 1/2 + tombol Cancel) memanggil `production_app.api.handover.create_request/cancel_request` dari client (endpoint tetap satu penulis ringkasan WO); picker = endpoint warehouse_app sendiri (`warehouse_app.warehouse_app.gudang_request.requestable_work_orders`, `frappe.get_list` Work Order — gudang punya read WO, tanpa bypass perm); papan Serah Terima Gudang ditambah kolom "Adonan" (left join WO via `custom_work_order`, display-only, diposisikan sebelum kolom WO); validasi box andalkan server. Konfigurasi site: Manufacturing Settings `custom_default_handover_warehouse` = "Gudang Barang Jadi - ROPI" (sebelumnya kosong).
- Gate `warehouse_app.tests.w9_gate.run_gate` → `ok:true` (16 checks): negative perm (picker & create ditolak untuk user tanpa role), picker menampilkan WO fixture dengan adonan + item_name + flag `request_active`, search adonan/item, `create_request` sebagai user gudang → MR submitted Material Transfer + row `custom_work_order` + ringkasan WO terisi, guard duplikat production_app menolak request kedua, papan menampilkan MR fixture (kolom Adonan idx-2, bucket Belum Dikirim), `cancel_request` → MR batal + ringkasan WO bersih, teardown residu 0. Guard umum `ok:true` (residu ZZTEST-W = 0; Custom DocPerm Company = baseline 12 baris).
- Temuan eksekusi: (1) Page desk butuh nama underscore murni — `scrub()` mengubah dash→underscore sehingga `load_assets` mencari folder/file `gudang_request`; page dinamai `gudang_request` (folder `page/gudang_request/`, file `gudang_request.js|css|json`), rute `/app/gudang_request`. (2) Setting serah terima production_app kosong di site ini — diset sekali sebagai konfigurasi (tercatat di R11), bukan kode warehouse_app. (3) Fixture WO/SE Manufacture: WO `ignore_validate` + docstatus manual; SE Manufacture butuh `expense_account` + `cost_center` di row FG.
- Review independen: APPROVE — 0 P0/P1; fix P2 diterapkan (normalisasi `search` non-string di picker; `on_page_show` reload agar badge "Diminta" tidak basi). 6 container sinkron + restart + ping pong; shortcut pertama workspace "Gudang" = "Request Serah Terima".
- **Revisi umpan balik user (2026-09-20, commit kedua)**: kartu diganti **tabel checklist full-width** — kolom Adonan/Item/Hasil/WO/Status sejajar, checkbox per baris + pilih-semua (indeterminate), baris klik-untuk-centang, baris "Diminta" non-selectable dengan tombol Batalkan, dan SATU aksi **"Buat Request (N)"** untuk 1..N WO (dialog alokasi Box per baris, jumlah prefilled = hasil WO; submit sekuensial dengan ringkasan sukses/gagal per WO). Panel kepadatan (Nyaman/Padat, persist di localStorage) di pojok kanan-bawah. Temuan eksekusi: `.layout-main` Desk v16 = flex row — konten page wajib dibungkus satu root full-width (ini juga penyebab tampilan kartu lama berantakan); `frappe.ui.keyCode` tidak ada di v16 (Enter search pakai `e.key`); dialog konfirmasi terbukti via browser fixture-user (login → tabel → multi-select → dialog → validasi kg kosong → search), lalu logout + purge sesi/user fixture. Gate + guard tetap `ok:true` pasca revisi.
