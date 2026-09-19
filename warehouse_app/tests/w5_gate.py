# Copyright (c) 2026, Muhammad Yusuf Tri Daryanto
# License: MIT

# Gate W5 — verifikasi eksekusi Workspace "Gudang" (Fase D).
#
# Jalankan:
#   docker exec erpnext-new-backend-1 bench --site frontend execute \
#       warehouse_app.tests.w5_gate.run_gate
#
# Kontrak output: TEPAT satu baris GATE_JSON:{...} (ok: bool, checks: dict,
# error: opsional). Cek gagal -> ok=false TANPA raise; hanya crash tak terduga
# yang di-raise (bench exit nonzero).
#
# Cek inti DARI DB (bukan file): baris Workspace "Gudang" (app/module/public/
# is_hidden), roles child "Has Role", shortcuts child "Workspace Shortcut",
# content (header + blok shortcut), dan count total Workspace pasca-migrate
# == 22 (baseline 21 nama terukur dari DB sebelum W5, 2026-09-20 — tercantum
# di BASELINE_WORKSPACES).
#
# Cek visibilitas memakai API desktop native (frappe.desk.desktop.get_workspaces)
# dengan SATU fixture user "ZZTEST-W5@example.com": tanpa role -> tak terlihat;
# + role Gudang Barang Jadi -> terlihat; ganti ke System Manager saja -> tak
# terlihat (is_permitted Workspace murni irisan roles — desktop.py:59-72;
# has_access hanya utk role "Workspace Manager" — desktop.py:359; jadi "terlihat
# System Manager" di TASKS.md hanya berlaku bila user itu juga di-pair role
# gudang, senada SOP pairing Stock User W7). Teardown lengkap di finally:
# User fixture + Sessions/Activity Log/Version-nya. Tanpa dokumen transaksi.

import json
import traceback

import frappe
from frappe.desk.desktop import get_workspaces as get_sidebar_workspaces

from warehouse_app.tests.guard import count_residue

WORKSPACE = "Gudang"
APP = "warehouse_app"
# Keputusan eskalasi W5 (2026-09-20): module workspace = "Stock" (native, asal
# MR/SE yang bisa dibaca user gudang) — allow_modules desktop dibangun dari
# modul DocType yang bisa dibaca user (desktop.py:40-43, user.py:157-178);
# app ini nol custom doctype sehingga modul "Warehouse App" tak pernah lolos
# gerbang itu. Kepemilikan app tetap di field APP di bawah.
MODULE = "Stock"
ROLE = "Gudang Barang Jadi"
HEADER_TEXT = "Gudang — Papan Serah Terima"
USER_EMAIL = "ZZTEST-W5@example.com"
PREFIX = "ZZTEST-W5"

EXPECTED_SHORTCUTS = {
    "Serah Terima Gudang": "Report",
    "Material Request": "DocType",
    "Stock Entry": "DocType",
    "Stock Balance": "Report",
}

# Baseline 21 workspace publik, terukur langsung dari DB site frontend
# (frappe.db.get_all Workspace, urut sequence_id) pada 2026-09-20 sebelum W5.
BASELINE_WORKSPACES = {
    "POSNext",
    "Production App",
    "Build",
    "Home",
    "Invoicing",
    "Financial Reports",
    "Buying",
    "Selling",
    "Stock",
    "Assets",
    "Manufacturing",
    "Subcontracting",
    "Quality",
    "Projects",
    "Support",
    "Users",
    "Website",
    "CRM",
    "ERPNext Settings",
    "Integrations",
    "Welcome Workspace",
}


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
            # Teardown tak boleh menggagalkan pencetakan GATE_JSON.
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

    # --- Preflight: prasyarat di DB ---
    missing = {
        "Module Def": not frappe.db.exists("Module Def", MODULE),
        "Role": not frappe.db.exists("Role", ROLE),
        "Report Serah Terima Gudang": not frappe.db.exists("Report", "Serah Terima Gudang"),
        "Report Stock Balance": not frappe.db.exists("Report", "Stock Balance"),
        "DocType Material Request": not frappe.db.exists("DocType", "Material Request"),
        "DocType Stock Entry": not frappe.db.exists("DocType", "Stock Entry"),
    }
    check("preflight", not any(missing.values()), f"hilang={sorted(k for k, v in missing.items() if v) or 'tidak ada'}")

    # --- Baris Workspace dari DB ---
    row = frappe.db.get_value(
        "Workspace",
        WORKSPACE,
        ["name", "label", "title", "app", "module", "public", "is_hidden", "for_user",
         "restrict_to_domain", "type", "sequence_id", "content"],
        as_dict=1,
    )
    if not row:
        check("workspace_row", False, f"Workspace {WORKSPACE!r} tidak ada di DB")
        return
    bad = {
        "label": row.label != WORKSPACE,
        "title": row.title != WORKSPACE,
        "app": row.app != APP,
        "module": row.module != MODULE,
        "public": row.public != 1,
        "is_hidden": row.is_hidden != 0,
        "for_user": bool(row.for_user),
        "restrict_to_domain": bool(row.restrict_to_domain),
        "type": row.type != "Workspace",
    }
    check(
        "workspace_row",
        not any(bad.values()),
        f"name={row.name!r} app={row.app!r} module={row.module!r} public={row.public} "
        f"is_hidden={row.is_hidden} sequence_id={row.sequence_id} | salah={sorted(k for k, v in bad.items() if v) or 'tidak ada'}",
    )

    # --- Roles child dari DB: tepat satu, Gudang Barang Jadi ---
    db_roles = sorted(frappe.get_all(
        "Has Role",
        filters={"parenttype": "Workspace", "parent": WORKSPACE},
        pluck="role",
    ))
    check(
        "workspace_roles",
        db_roles == [ROLE],
        f"roles DB={db_roles} (harap tepat [{ROLE!r}])",
    )

    # --- Shortcuts child dari DB: >= 1 (kontrak gate) + set 4 shortcut sesuai desain ---
    db_sc = {
        s.label: s.type
        for s in frappe.get_all(
            "Workspace Shortcut",
            filters={"parenttype": "Workspace", "parent": WORKSPACE},
            fields=["label", "type"],
        )
    }
    check("shortcuts_min_1", len(db_sc) >= 1, f"{len(db_sc)} shortcut di DB")
    sc_bad = sorted(f"{lbl}:{typ}" for lbl, typ in db_sc.items() if EXPECTED_SHORTCUTS.get(lbl) != typ)
    missing_sc = sorted(set(EXPECTED_SHORTCUTS) - set(db_sc))
    check(
        "shortcuts_expected_set",
        not sc_bad and not missing_sc,
        f"DB={db_sc} | salah_type={sc_bad} | hilang={missing_sc}",
    )

    # --- Content dari DB: header pendek + 4 blok shortcut ---
    try:
        blocks = json.loads(row.content)
        headers = [b["data"]["text"] for b in blocks if b.get("type") == "header"]
        sc_names = [b["data"]["shortcut_name"] for b in blocks if b.get("type") == "shortcut"]
        content_ok = (
            any(HEADER_TEXT in h for h in headers)
            and sorted(sc_names) == sorted(EXPECTED_SHORTCUTS)
        )
        check(
            "workspace_content",
            content_ok,
            f"headers={headers} shortcut_blocks={sc_names}",
        )
    except Exception as e:
        check("workspace_content", False, f"{type(e).__name__}: {e}")

    # --- Tidak ada Workspace lain yang berubah: count total == 22 dan nama == baseline+Gudang ---
    db_names = set(frappe.get_all("Workspace", pluck="name"))
    check(
        "workspace_total_count",
        len(db_names) == len(BASELINE_WORKSPACES) + 1,
        f"total DB={len(db_names)} (harap {len(BASELINE_WORKSPACES) + 1} = baseline 21 + Gudang); "
        f"beda_dgn_baseline+Gudang={sorted(db_names ^ (BASELINE_WORKSPACES | {WORKSPACE})) or 'tidak ada'}",
    )
    ours = sorted(frappe.get_all("Workspace", filters={"app": APP}, pluck="name"))
    check("workspace_app_scope", ours == [WORKSPACE], f"Workspace app {APP}!r={ours}")

    # --- Ikon nav /desk (Desktop Icon) yang menunjuk grup sidebar Gudang ---
    # Nav atas /desk dirender dari Desktop Icon link_type "Workspace Sidebar"
    # (temuan W6: tanpa ikon ini, grup Gudang ada di boot tapi tak dirender).
    try:
        from warehouse_app.upgrade import ensure_desktop_icon

        ensure_desktop_icon()
        icon = frappe.db.get_value(
            "Desktop Icon",
            {"label": WORKSPACE},
            ["link_type", "link_to", "app"],
            as_dict=1,
        )
        ok = bool(
            icon
            and icon.link_type == "Workspace Sidebar"
            and icon.link_to == WORKSPACE
            and icon.app == APP
        )
        check(
            "desktop_icon_gudang",
            ok,
            f"icon={(icon.link_type, icon.link_to, icon.app) if icon else None}",
        )
    except Exception as e:
        check("desktop_icon_gudang", False, f"{type(e).__name__}: {str(e)[:180]}")

    # --- Visibilitas via API desktop native + fixture user 1 buah ---
    if not (frappe.db.exists("Role", ROLE)):
        return
    try:
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": USER_EMAIL,
                "first_name": PREFIX,
                "user_type": "System User",
                "desk_access": 1,
                "send_welcome_email": 0,
                "new_password": frappe.generate_hash(length=16),
            }
        )
        user.flags.ignore_permissions = True
        user.insert()
    except Exception as e:
        check("fixture_user", False, f"{type(e).__name__}: {e}")
        return

    def sidebar_has_gudang():
        pages = get_sidebar_workspaces()["pages"]
        names = sorted(p.name for p in pages)
        return WORKSPACE in names, names

    # Cache desktop per-user TIDAK ikut dihapus clear_cache(user=...) semua:
    # "user_allowed_modules" TTL 6 jam (desktop.py:35,84) tak tercantum di
    # user_cache_keys (cache_manager.py) — bila tak dihapus eksplisit, sidebar
    # memakai snapshot modul user SEBELUM perubahan role.
    def _clear_desktop_cache():
        frappe.clear_cache(user=USER_EMAIL)
        frappe.cache.delete_value(
            ("user_allowed_modules", "user_perm_can_read", "allowed_dashboards"),
            user=USER_EMAIL,
        )

    # 1) tanpa role gudang -> TIDAK terlihat
    frappe.set_user(USER_EMAIL)
    try:
        _clear_desktop_cache()
        has_g, names = sidebar_has_gudang()
        check(
            "sidebar_hidden_without_role",
            not has_g,
            f"roles={frappe.get_roles(USER_EMAIL)}; pages={names}",
        )
    except Exception as e:
        check("sidebar_hidden_without_role", False, f"{type(e).__name__}: {str(e)[:180]}")

    # 2) + role gudang -> terlihat
    try:
        frappe.set_user("Administrator")
        doc = frappe.get_doc("User", USER_EMAIL)
        doc.flags.ignore_permissions = True
        doc.add_roles(ROLE)
        _clear_desktop_cache()
        frappe.set_user(USER_EMAIL)
        has_g, names = sidebar_has_gudang()
        check(
            "sidebar_visible_with_role",
            has_g,
            f"roles={frappe.get_roles(USER_EMAIL)}; pages={names}",
        )
        # 2b) Item sidebar yang BENAR-BENAR dirender Desk (boot.workspace_sidebar_item).
        # get_workspaces hanya membuktikan izin workspace; grup sidebar hanya tampil
        # bila ada Workspace Sidebar yang ber-item menunjuk workspace itu
        # (frappe/boot.py:442-496 get_sidebar_items + is_item_allowed per item).
        try:
            from frappe.boot import get_sidebar_items

            sidebars = get_sidebar_items(names)
            found = sorted(
                f"{title}:{it.get('label')}"
                for title, grp in sidebars.items()
                for it in grp.get("items", [])
                if it.get("link_type") == "Workspace" and it.get("link_to") == WORKSPACE
            )
            check("sidebar_item_gudang", bool(found), f"item={found or 'tidak ada'}")
        except Exception as e2:
            check("sidebar_item_gudang", False, f"{type(e2).__name__}: {str(e2)[:180]}")
    except Exception as e:
        check("sidebar_visible_with_role", False, f"{type(e).__name__}: {str(e)[:180]}")

    # 3) System Manager TANPA role gudang -> TIDAK terlihat (roles murni irisan;
    #    has_access hanya utk "Workspace Manager"). "Terlihat System Manager" di
    #    TASKS.md berlaku via pairing role gudang, senada SOP W7.
    try:
        frappe.set_user("Administrator")
        doc = frappe.get_doc("User", USER_EMAIL)
        doc.flags.ignore_permissions = True
        doc.roles = [r for r in doc.roles if r.role != ROLE]
        doc.add_roles("System Manager")
        doc.save()
        _clear_desktop_cache()
        frappe.set_user(USER_EMAIL)
        has_g, names = sidebar_has_gudang()
        check(
            "sidebar_hidden_sm_without_gudang_role",
            not has_g,
            f"roles={frappe.get_roles(USER_EMAIL)}; pages={names}",
        )
    except Exception as e:
        check("sidebar_hidden_sm_without_gudang_role", False, f"{type(e).__name__}: {str(e)[:180]}")
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
    """Bersihkan semua residu ber-prefix ZZTEST-W5. Idempoten (pre-clean & teardown)."""
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
    # kolom Version di v16: ref_doctype + docname
    safe("Version", lambda: frappe.db.delete("Version", {"docname": ("like", PREFIX + "%")}))
    safe("Note", lambda: frappe.db.delete("Note", {"title": ("like", PREFIX + "%")}))

    return (not errors), ("bersih" if not errors else "; ".join(errors[:5]))
