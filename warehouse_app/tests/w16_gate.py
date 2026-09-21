# Copyright (c) 2026, Muhammad Yusuf Tri Daryanto
# License: MIT

# Gate W16 — verifikasi eksekusi "sidebar sendiri" (isi Workspace Sidebar Gudang).
#
# Jalankan:
#   docker exec erpnext-new-backend-1 bench --site frontend execute \
#       warehouse_app.tests.w16_gate.run_gate
#
# Kontrak output: TEPAT satu baris GATE_JSON:{...} (pola w5_gate).
#
# Cek inti DARI DB (bukan file): Workspace Sidebar "Gudang" (app/standard/
# header_icon) + child items == 4 item desain W16 (Gudang/Handover Requests/
# Serah Terima Gudang/Settings, dgn link_type & icon & idx). Idempotensi:
# ensure_workspace_sidebar() kedua kali harus "unchanged". Render nyata via
# frappe.boot.get_sidebar_items dengan DUA fixture user ber-email UNIK per run
# (cache redis per-email dari run lama bisa membusukkan render — lihat catatan
# di _run_gate): tanpa role -> grup Gudang tak tampil; role Gudang Barang Jadi
# + Stock User (SOP pairing W7) -> grup + 4 item tampil. Desktop Icon penunjuk
# grup ikut dicek (temuan W6). Teardown residu ZZTEST-W16 = 0.

import json
import time
import traceback

import frappe
from frappe.boot import get_sidebar_items
from frappe.desk.desktop import get_workspaces as get_sidebar_workspaces

from warehouse_app.tests.guard import count_residue
from warehouse_app.upgrade import SIDEBAR_ITEMS, ensure_workspace_sidebar

SIDEBAR = "Gudang"
APP = "warehouse_app"
ROLE = "Gudang Barang Jadi"
PREFIX = "ZZTEST-W16"

# Pasangan (label, link_type, link_to, icon) yang wajib dirender untuk user gudang.
EXPECTED_RENDER = sorted(
    (it["label"], it["link_type"], it["link_to"], it["icon"]) for it in SIDEBAR_ITEMS
)


def run_gate():
    checks = {}
    error = None

    def check(name, ok, evidence):
        checks[name] = str(evidence) if ok else f"GAGAL: {evidence}"

    try:
        _run_gate(check)
    except Exception:
        error = traceback.format_exc()
    finally:
        try:
            _teardown(check)
        except Exception as te:
            check("teardown", False, f"teardown error {type(te).__name__}: {te}")
        payload = {
            "ok": error is None and not any(v.startswith("GAGAL") for v in checks.values()),
            "checks": checks,
        }
        if error:
            payload["error"] = error[-2000:]
        print("GATE_JSON:" + json.dumps(payload, ensure_ascii=False))

    if error:
        raise SystemExit(1)


def _run_gate(check):
    check("pre_clean", *_sweep())

    # --- Sinkron idempoten: jalankan sebelum assert DB ---
    try:
        result = ensure_workspace_sidebar()
        check("ensure_synced", result in ("created", "synced", "unchanged"), f"apply#{1} -> {result}")
        result2 = ensure_workspace_sidebar()
        check("ensure_idempotent", result2 == "unchanged", f"apply#{2} -> {result2}")
    except Exception as e:
        check("ensure_synced", False, f"{type(e).__name__}: {str(e)[:200]}")
        return

    # --- Baris Workspace Sidebar dari DB ---
    row = frappe.db.get_value(
        "Workspace Sidebar", SIDEBAR, ["app", "standard", "header_icon"], as_dict=1
    )
    bad = {
        "exists": not row,
        "app": bool(row) and row.app != APP,
        "standard": bool(row) and row.standard != 1,
        "header_icon": bool(row) and row.header_icon != "package",
    }
    check(
        "sidebar_row",
        not any(bad.values()),
        f"app={row.app if row else None} standard={row.standard if row else None} "
        f"header_icon={row.header_icon if row else None} | salah={sorted(k for k, v in bad.items() if v) or 'tidak ada'}",
    )

    # --- Child items dari DB: tepat 4 sesuai desain ---
    db_items = [
        {
            "label": r.label,
            "link_to": r.link_to,
            "link_type": r.link_type,
            "type": r.type,
            "icon": r.icon,
            "idx": r.idx,
        }
        for r in frappe.get_all(
            "Workspace Sidebar Item",
            filters={"parenttype": "Workspace Sidebar", "parent": SIDEBAR},
            fields=["label", "link_to", "link_type", "type", "icon", "idx"],
            order_by="idx",
        )
    ]
    check("sidebar_items_db", db_items == SIDEBAR_ITEMS, f"items DB={db_items}")

    # --- Desktop Icon penunjuk grup (temuan W6) ---
    icon = frappe.db.get_value(
        "Desktop Icon", {"label": SIDEBAR}, ["link_type", "link_to", "app"], as_dict=1
    )
    check(
        "desktop_icon_gudang",
        bool(icon and icon.link_type == "Workspace Sidebar" and icon.link_to == SIDEBAR and icon.app == APP),
        f"icon={(icon.link_type, icon.link_to, icon.app) if icon else None}",
    )

    # --- Render nyata via boot dengan fixture user ---
    # Email fixture UNIK per run: cache redis (doc cache global User, hash roles,
    # allowed-reports TTL 6 jam) ber-key email dan BISA bertahan sisa run lama
    # (fosil user_type menjatuhkan role Desk User otomatis -> has_permission
    # "Report" false -> item Report tak dirender). Email segar = bebas fosil.
    # Masing-masing fixture dirender SEKALI tepat setelah dibuat (role sejak
    # insert); transisi role setelah render pertama bukan cakupan gate ini.
    if not frappe.db.exists("Role", ROLE):
        check("fixture_role", False, f"Role {ROLE!r} tidak ada")
        return

    def _make_user(email, first_name, roles):
        doc = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": first_name,
                "user_type": "System User",
                "send_welcome_email": 0,
                "new_password": frappe.generate_hash(length=16),
                "roles": [{"role": r} for r in roles],
            }
        )
        doc.flags.ignore_permissions = True
        doc.insert()
        frappe.clear_cache(user=email)

    def rendered_items():
        names = sorted(p.name for p in get_sidebar_workspaces()["pages"])
        sidebars = get_sidebar_items(names)
        found = set()
        for grp in sidebars.values():
            for it in grp.get("items", []):
                quad = (it.get("label"), it.get("link_type"), it.get("link_to"), it.get("icon"))
                if quad[2] in {e[2] for e in EXPECTED_RENDER}:
                    found.add(quad)
        # dedup: link yang sama bisa muncul di Workspace Sidebar kita DAN di
        # sidebar modul auto-generate; yang dinilai hanya liputan itemnya.
        return sorted(found)

    run_id = int(time.time())
    no_role_email = f"ZZTEST-W16-NR-{run_id}@example.com"
    user_email = f"ZZTEST-W16-{run_id}@example.com"

    # 1) user tanpa role gudang -> tidak ada item grup Gudang
    try:
        _make_user(no_role_email, PREFIX + "-NR", [])
        frappe.set_user(no_role_email)
        check("hidden_without_role", rendered_items() == [], f"items={rendered_items()}")
    except Exception as e:
        check("hidden_without_role", False, f"{type(e).__name__}: {str(e)[:180]}")
    finally:
        frappe.set_user("Administrator")

    # 2) user gudang + pairing Stock User (SOP W7) -> 4 item sesuai desain
    try:
        _make_user(user_email, PREFIX, [ROLE, "Stock User"])
        frappe.set_user(user_email)
        items = rendered_items()
        check(
            "render_with_pairing",
            items == EXPECTED_RENDER,
            f"items={items} | harap={EXPECTED_RENDER}",
        )
    except Exception as e:
        check("render_with_pairing", False, f"{type(e).__name__}: {str(e)[:180]}")
    finally:
        frappe.set_user("Administrator")


def _teardown(check):
    try:
        frappe.set_user("Administrator")
    except Exception:
        pass
    sweep_ok, sweep_evidence = _sweep()
    residue = count_residue(PREFIX)
    zero = all(v == 0 for v in residue.values())
    check("teardown", sweep_ok and zero, f"{sweep_evidence}; residu {PREFIX}={residue}")


def _sweep():
    """Bersihkan semua residu ber-prefix ZZTEST-W16. Idempoten (pre-clean & teardown)."""
    errors = []

    def safe(label, fn):
        try:
            fn()
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}: {str(e)[:120]}")

    for name in frappe.get_all("User", filters={"name": ("like", PREFIX + "%")}, pluck="name"):
        safe(f"User {name}", lambda n=name: frappe.delete_doc("User", n, force=1, ignore_missing=True))
    safe("Sessions", lambda: frappe.db.delete("Sessions", {"user": ("like", PREFIX + "%")}))
    safe("ActivityLog.user", lambda: frappe.db.delete("Activity Log", {"user": ("like", PREFIX + "%")}))
    if frappe.db.has_column("Activity Log", "for_user"):
        safe(
            "ActivityLog.for_user",
            lambda: frappe.db.delete("Activity Log", {"for_user": ("like", PREFIX + "%")}),
        )
    safe("Version", lambda: frappe.db.delete("Version", {"docname": ("like", PREFIX + "%")}))

    return (not errors), ("bersih" if not errors else "; ".join(errors[:5]))
