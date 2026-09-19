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

## W6 — E2E walkthrough + residu 0 + guard perm (Fase E) — PENDING
Depends: W3-W5. Walkthrough browser (fixture user, bukan akun asli): papan → SE → submit → papan update. Residu fixture = 0 (dokumen uji, user uji, Sessions/Activity Log). Guard R7/R6: `Custom DocPerm` parent "Company" tetap kosong + Stock User masih read Company pasca-migrate.
Gate: bukti walkthrough + hasil query residu & guard tercatat di `PROJECT_STATE.md`.

## W7 — Company read utk Gudang Barang Jadi (PARKIR)
Trigger: user memutuskan gudang single-role tanpa Stock User. `frappe.permissions.add_permission` (Company saja, additive-only, idempotent) di `after_migrate` + test replacement-trap. Default: tidak dieksekusi (SOP pairing Stock User).

## W8 — Smoke test endpoint dormant production_app (PARKIR, non-W2)
Trigger: kapan pun setelah W6. Panggil `create_request`/`cancel_request`/`fulfill_form_order` (production_app) dengan fixture, pastikan tak membusuk, bersihkan residu.
