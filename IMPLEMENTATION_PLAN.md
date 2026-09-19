# IMPLEMENTATION_PLAN — warehouse_app

Rencana fitur pertama. Sumber aturan: `AGENTS.md` (batasan keras berlaku ke semua fase). Disusun sesi planning 2026-09-20; rulings advisor tercatat di §3.
Eksekusi nanti per task W# di `TASKS.md` (subagent-driven atau executing-plans; satu entri = satu commit, bukti eksekusi wajib sebelum DONE).

**Goal:** Gudang barang jadi punya papan serah terima di Desk (read dari dokumen native) + aksi buat Stock Entry via mapper native — tanpa menyentuh native ERPNext maupun alur produksi.

**Arsitektur:** Desk-first. Nol custom doctype, nol frontend build, nol endpoint tulis. Satu Script Report (derivasi status server-side dari `per_ordered` native) + client script aksi + Workspace "Warehouse App" role-scoped.

**Tech stack:** Frappe/ERPNext v16 (Docker, site `frontend`), modul "Warehouse App", Python + JS client report + workspace JSON.

---

## 1. Requirements vs desain

| Kebutuhan | Desain | Rujukan |
|---|---|---|
| Gudang lihat MR serah terima per WO: belum dikirim / sebagian / terkirim | Script Report **"Serah Terima Gudang"**, grain = Material Request Item, bucket dari `per_ordered` native (server-side Python) | R3, verifikasi §4 |
| Aksi kirim dari papan | Tombol per baris → `frappe.model.open_mapped_doc` ke mapper native `make_stock_entry`; validasi batch/stok/over-qty tetap native saat save/submit SE | R5, `material_request.py:935` (whitelisted) |
| MR yatim (pasca-FU57, tanpa `custom_work_order`) tetap terlihat | Filter papan = arah gudang (`t_warehouse`), **bukan** keberadaan field custom; kolom WO display-only (kosong utk yatim = fitur) | R3, R4 |
| Rumah gudang di Desk | Workspace publik ber-`roles` "Gudang Barang Jadi" (+ Stock Manager implisit lihat), shortcut ke report & list native | R1; field `roles` terverifikasi ada di Workspace v16 |
| Role gudang murni tak bisa read Company | SOP: pairing role `Stock User` (nol kode, praktik berjalan). Fallback kode = W7 (PARKIR) | R6, R7; `company.json:1078-1080` |
| Tahan terhadap dua app di satu site | Larangan cross-import production_app; nol doc_events baru di MR/SE; field custom production_app = display-only, bukan filter/status/tulis | R2, R4, R8, R10 |

## 2. Keputusan terkunci (user, 2026-09-20)

1. **Desk-first** — SPA baru kalau alur mentok di Desk.
2. **Endpoint dormant tidak dipindah** — produksi tetap buat/kirim via production_app; warehouse_app konsumsi dokumen native yang sama.
3. **Fitur W2 = papan serah terima gudang.**
4. **Perbaikan role/perm mengikuti kebutuhan fitur** — bukan revamp.

## 3. Rulings advisor (2026-09-20)

- **R1** Desk-first disetujui; derivasi status wajib server-side Python; client script hanya render/route; workspace role-scoped.
- **R2** Endpoint dormant tetap di production_app; **warehouse_app dilarang cross-import Python production_app**; smoke test endpoint = task parkir.
- **R3** Papan = script report; status dari `per_ordered`/`status` **native** (bukan `custom_handover_status` di WO); grain MR Item; filter arah gudang via report filter, nama gudang tidak di-hardcode di logika.
- **R4** Field custom production_app = dekorasi opsional: dilarang jadi kunci filter, sumber status, atau target tulis; MR yatim tampil di papan.
- **R5** Aksi buat SE = mapper native + redirect ke SE draft; **tanpa endpoint custom**; batch dipilih manual via selector FIFO native (mapper tidak mem-map `batch_no` — diterima sebagai perilaku W2).
- **R6** Perm W2 = pairing `Stock User` (nol kode); fallback: `frappe.permissions.add_permission` utk Company oleh warehouse_app, additive-only & idempotent.
- **R7** Kepemilikan DocPerm **per doctype satu pemilik** (MR/SE/WO/Item/Batch/Warehouse milik production_app); warehouse_app boleh ensure role "Gudang Barang Jadi" ada; wajib test replacement-trap (Custom DocPerm menggantikan seluruh DocPerm standar doctype — `frappe/permissions.py:512`).
- **R8** Audit doc_events production_app tidak menulis field tracking native — **sudah dilakukan di sesi planning (W2, lihat §4)**.
- **R9** MR dianggap selesai tapi `per_ordered < 100` ditutup via aksi native **Stop MR** — SOP, bukan kode; tanpa auto-close custom. Konsekuensi "partial = terkirim penuh" (keputusan produksi) vs `per_ordered` (papan) diterima dan didokumentasikan.
- **R10** W2 menambah **nol doc_events** di MR/SE; report qty-only tanpa valuasi/cost; role report: Gudang Barang Jadi + Stock Manager.

## 4. Dasar desain — verifikasi source v16 (verbatim, sesi planning 2026-09-20)

- Mapper native ber-whitelist: `@frappe.whitelist()` di atas `def make_stock_entry(source_name, target_doc=None)` — `erpnext/stock/doctype/material_request/material_request.py:935-936`. Qty ter-map = sisa pending (`stock_qty - ordered_qty`); `batch_no` tidak ter-map.
- Over-qty ditolak atomik saat SE submit: `material_request.py:424-429` (pesan "…cannot be greater than requested quantity…"), kecuali Stock Settings `mr_qty_allowance`. SE update MR via hook `erpnext/hooks.py:358-359`; status MR → "Transferred" saat `per_ordered==100` (`status_updater.py:125-127`).
- Batch wajib utk item `has_batch_no` saat submit: `stock_ledger_entry.py:325-327`; batch expired **tidak** divalidasi utk purpose Material Transfer (`stock_controller.py:353,372`).
- Custom DocPerm replacement: `frappe/permissions.py:512` (`custom_perms = get_perms_for(roles, "Custom DocPerm")`) — begitu satu doctype punya Custom DocPerm, perms standar doctype itu diabaikan (dasar R7).
- Workspace v16 punya `roles`, `parent_page`, `is_hidden`, `content` (blok JSON) — daftar field diambil langsung dari `frappe/desk/doctype/workspace/workspace.json`; dikirim via `<app>/<module>/workspace/<name>/<name>.json`.
- Stock Reconciliation hanya untuk role Stock Manager (`stock_reconciliation.json:201-213`) — relevan utk fitur opname di masa depan.
- **Audit mirror production_app (R8, selesai)**: `sync_from_material_request`/`sync_from_stock_entry` (`production_app/api/handover.py:735-777`) fail-safe (log_error, tidak pernah raise) dan hanya menulis ke Work Order via `frappe.db.set_value("Work Order", …)` (`handover.py:723,1249`) — field tracking native MR/SE (`ordered_qty`, `status`, `per_ordered`) tidak disentuh.

**Klarifikasi domain** (AGENTS.md meringkas jadi satu; ini hasil verifikasi kode): **Serah terima barang jadi** = MR Material Transfer bertaut WO (`custom_work_order` di MR Item), dibuat gudang via endpoint dormant `create_request` atau manual Desk, dikirim produksi via `send_handover` (aktif) atau Desk. **Form Order** (`custom_is_form_order`) = permintaan **bahan** produksi→gudang, bebas tanpa WO, difulfill gudang via `fulfill_form_order` (dormant) atau Desk. Papan W2 hanya menyangkut serah terima barang jadi; pemisah domain di papan = arah gudang (`t_warehouse`), bukan `custom_is_form_order`.

## 5. Fase & gate

### Fase A — Verifikasi pradesain (W2) — **DONE**
Empat verifikasi §4 dieksekusi via `docker exec`/grep saat planning; bukti file:line tercatat di atas dan di `TASKS.md` W2.

### Fase B — Script Report "Serah Terima Gudang" (W3)
Files (modul "Warehouse App", folder modul `warehouse_app/warehouse_app/`):
- Create `warehouse_app/warehouse_app/warehouse_app/__init__.py` + `…/warehouse_app/report/__init__.py` (folder modul kini kosong)
- Create `…/warehouse_app/report/serah_terima_gudang/{__init__.py, serah_terima_gudang.json, serah_terima_gudang.py}`

Desain report:
- JSON: `report_type: "Script Report"`, `ref_doctype: "Material Request"`, `is_standard: "Yes"`, `module: "Warehouse App"`, roles: `Gudang Barang Jadi`, `Stock Manager`.
- **Keputusan eksekusi W3 (2026-09-20, ruling orchestrator):** `ref_doctype` diubah menjadi **"Stock Entry"** — gerbang perm native `query_report.run` (`frappe/desk/query_report.py:40-45`) menuntut ptype `report` pada ref_doctype, sedangkan Custom DocPerm Material Request (pemilik production_app, R7) men-set `report=0` untuk semua role gudang (bukti: PermissionError "You don't have permission to get a report on: Material Request" pada gate W3). Stock Entry dipilih karena Custom DocPerm SE ber-`report=1` untuk Stock User; data papan tetap Material Request; nol perubahan DocPerm; reversible satu field JSON.
- Query (server-side Python): MR Item `docstatus=1` join MR `docstatus=1`, `material_request_type="Material Transfer"`, `t_warehouse` = filter **Gudang Tujuan** (default `"Gudang Barang Jadi - ROPI"` — nama eksak site; default filter bukan logika hardcoded, dan `resolve_warehouse` tetap menerima bentuk tanpa abbr. Catatan eksekusi W6: Link filter menuntut nilai valid eksak — nilai tanpa abbr ditolak client "Warehouse … not found"). Tanpa filter pada field custom apa pun.
- Bucket status: `ordered_qty==0` → "Belum Dikirim"; `0<per_ordered<100` → "Sebagian"; `per_ordered==100` → "Terkirim". Kolom native `status` MR ditampilkan apa adanya (termasuk "Stopped" — SOP R9).
- Kolom: MR (link), Tanggal, Work Order (display-only, boleh kosong), Item Code/Name, Qty Diminta (`stock_qty`), Sudah Dikirim (`ordered_qty`), Sisa, UOM, Gudang Tujuan, Box 1/Box 2 (dari MR header, display-only), Status Papan, Status MR. **Qty-only, tanpa valuasi.**

**Gate B (eksekusi):** `bench --site frontend migrate` sukses; report terdaftar & ter-query via API sebagai fixture user ber-role gudang; 3 kasus derivasi benar atas data uji fixture (MR belum dikirim, sebagian, penuh — dibuat lalu dibersihkan); tidak ada kolom valuasi; user tanpa role ditolak.

### Fase C — Aksi buat SE dari papan (W4)
- Create `…/serah_terima_gudang/serah_terima_gudang.js`: formatter chip status + kolom Aksi (tombol "Buat Stock Entry" utk bucket Belum/Sebagian) → `frappe.model.open_mapped_doc({method: "erpnext.stock.doctype.material_request.material_request.make_stock_entry", source_name: <row MR>})`. Fallback jika tombol in-report rapuh: kolom MR link → tombol native Create▸Stock Entry di form MR (2 klik); putusan implementer dicatat di bukti W4.

**Gate C (eksekusi):** aksi membuka SE draft berisi item sisa; simpan+submit native sukses; percobaan over-qty ditolak native (pesan §4); setelah submit, baris papan pindah bucket tanpa restart app; tidak ada endpoint baru di repo warehouse_app.

### Fase D — Workspace "Warehouse App" (W5)
- Create `…/warehouse_app/workspace/gudang/gudang.json` (folder workspace per pola v16): `public: 1`, `roles: [Gudang Barang Jadi]`, `app: "warehouse_app"`, shortcut: report Serah Terima Gudang + list Material Request (filter Material Transfer) + list Stock Entry + link Stock Balance. Content blok header sederhana.
- **Keputusan eksekusi W6 (temuan walkthrough):** nav atas /desk dirender dari **Desktop Icon → Workspace Sidebar** — tanpa keduanya grup "Gudang" tidak dirender walau workspace diizinkan (`boot.workspace_sidebar_item` memuat, render tetap butuh ikon; `frappe/boot.py:442-496` + `utils.js:1321`). Fix: `workspace_sidebar/gudang/gudang.json` + `upgrade.py` idempoten (`ensure_workspace_sidebar` + `ensure_desktop_icon`, dijalankan after_install/after_migrate; pola `production_app.upgrade.ensure_desktop_icon:1430-1452`).
- **Keputusan eksekusi W5 (2026-09-20, eskalasi orchestrator):** field `module` di gudang.json = **"Stock"** (modul native asal Material Request/Stock Entry), bukan "Warehouse App" — sidebar desktop menolak workspace bila `doc.module` tidak ada di `allow_modules` user, dan `allow_modules` dibangun murni dari modul DocType yang bisa dibaca user (`frappe/desk/desktop.py:40-43`, `frappe/utils/user.py:157-178`); app ini nol custom doctype sehingga modul "Warehouse App" tak pernah masuk (bukti: probe gate W5 — module "Warehouse App" → workspace tak tampak; "Stock" → tampak). Preceden: workspace "Production App" di site ini ber-module "Manufacturing". Kepemilikan tetap tercatat di field `app`; caveat: bila kelak app di-uninstall, workspace ini tidak ikut terhapus via mekanisme modul — hapus manual.

**Gate D (eksekusi):** setelah migrate, workspace muncul di sidebar user role gudang & System Manager; shortcut berfungsi; user tanpa role tidak melihatnya (cek API desktop); JSON workspace tersinkron ke 6 container (pipeline deploy AGENTS.md).

### Fase E — E2E & kebersihan (W6)
Walkthrough UI di browser sesi utama (fixture user, bukan akun asli): papan → buat SE → submit → papan update. Lalu: residu fixture = 0 (dokumen uji cancel+delete, user uji, Sessions/Activity Log) dan guard R7/R6: `Custom DocPerm` parent "Company" **identik baseline tercatat** di `warehouse_app/tests/guard.py` — 12 baris pre-existing (9× 2022-01-25, 2× Feb-2026 Administrator; 1× "ALL ROLE" 2026-09-08 ropierpnext@gmail.com), nol dari warehouse_app; re-scope reviewer pasca-W3 karena premis "harus tetap kosong" tidak cocok realitas situs (guard false permanen / menggoda hapus perm milik pihak lain — langgar R7) + `Stock User` masih punya read Company pasca-migrate.

**Gate E (eksekusi):** bukti walkthrough (screenshot/log fetch) + hasil query residu = 0 + hasil guard tercatat di `PROJECT_STATE.md`.

## 6. Yang sengaja TIDAK berubah

- Kode production_app apa pun: endpoint dormant, doc_events mirror, matriks DocPerm MR/SE/WO/Item/Batch/Warehouse, SPA produksi.
- Perilaku native MR/SE/Batch/WO: tidak ada custom field baru di dokumen native, tidak ada property setter, tidak ada guard.
- Tidak ada doc_events baru warehouse_app di MR/SE (R10) — papan murni derivasi saat baca.
- Tidak ada auto-close MR, tidak ada prefill batch otomatis (R5, R9).
- Alur serah terima produksi→gudang & Form Order tetap milik production_app (keputusan user #2).

## 7. Parkir (bukan scope Fase B–E)

- **W7** (PARKIR — trigger: user memutuskan gudang single-role tanpa Stock User): Company read via `frappe.permissions.add_permission`, additive-only, idempotent, di `after_migrate`; + test replacement-trap R7.
- **W8** (PARKIR, non-W2 per R2): smoke test endpoint dormant production_app (`create_request`/`cancel_request`/`fulfill_form_order`) agar tidak membusuk diam-diam.
- SPA warehouse, opname/counting, MR gudang ke produksi, migrasi alur serah terima — sesi planning berikutnya, bila Desk mentok atau kebutuhan muncul.

## 8. Risiko & mitigasi (dari advisor §E)

1. **Partial = terkirim penuh (SOP produksi) vs `per_ordered` (papan)** → baris "Sebagian" abadi untuk MR yang produksi anggap selesai. Mitigasi SOP: Stop MR native + konfirmasi sebelum SE kedua. Tidak dikodekan (R9).
2. **Rantai doc_events dua app** → W2 nol doc_events baru (R10); bila kelak perlu: never-raise, hanya tulis data milik sendiri.
3. **Query report bypass perm doctype** → role report eksplisit (R10), qty-only, tanpa join valuasi; user tanpa role ditolak (Gate B).
