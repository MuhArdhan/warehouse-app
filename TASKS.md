# TASKS — warehouse_app

Custom app untuk org gudang (finished-goods warehouse). Keputusan FU57 (production_app, 2026-09-20): native ERPNext harus bebas dari pengaruh custom app manufacturing; production_app fokus user manufacturing; tooling gudang = app terpisah ini.

## W1 — Scaffold + install di site frontend — DONE (2026-09-20)
- `bench new-app warehouse_app` di container backend (title "Warehouse App", license mit), lalu `bench --site frontend install-app warehouse_app` (site yang sama dengan production_app).
- Kode host = repo ini. Sinkron ke container via docker cp (folder `apps/` bukan bind mount) ke 6 container frappe: backend, frontend, queue-short, queue-long, scheduler, websocket + chown frappe:frappe.
- 4 container non-backend (queue×2, scheduler, websocket) juga perlu `production_app.pth` + `warehouse_app.pth` + dist-info di `env/lib/python3.14/site-packages` (image hanya pernah pip-install frappe+erpnext) — disalin dari backend.
- Bukti: `bench --site frontend list-apps` → warehouse_app 0.0.1 tercantum; `frappe.get_installed_apps` terbaca dari scheduler; `import warehouse_app` OK dari python worker queue (queue-short) versi 0.0.1; `ping` → pong; home 200.
- Heal utang lama (side effect W1): container queue/scheduler/websocket tidak pernah punya kode `production_app` (ModuleNotFoundError tiap boot worker sejak image dibangun). Kode + .pth production_app kini disalin ke 4 container itu. Sisa pre-existing, tidak diketuk: `pos_next`, `bakery_manufacturing`, `email_delivery_service` juga tidak ada di container queue (error non-fatal, worker tetap jalan).

## Next
- Menunggu arah fitur gudang dari user (belum ada doctype/API/UI).
