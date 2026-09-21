# Copyright (c) 2026, Muhammad Yusuf Tri Daryanto
# License: MIT

# Pemasangan idempoten non-doctype warehouse_app (after_install & after_migrate).
# Pola mengikuti production_app.upgrade (satu app satu kepemilikan data; R7).
#
# Konteks W6: nav atas /desk dirender dari dokumen Desktop Icon yang menunjuk
# Workspace Sidebar (link_type "Workspace Sidebar"); grup "Gudang" hanya tampak
# bila keduanya ada. File JSON workspace_sidebar/gudang/gudang.json tetap sumber
# sync; fungsi di sini jaring pengaman idempoten.

import frappe

SIDEBAR = "Gudang"
APP = "warehouse_app"
ROLE = "Gudang Barang Jadi"
SIDEBAR_ICON = "package"

# Nav grup "Gudang" di sidebar Desk. Icon = nama set lucide frappe v16
# (icon-<name> di public/icons/lucide/icons.svg); "package" dipakai bersama
# Desktop Icon & workspace agar satu identitas. Selaras JSON sync:
# warehouse_app/warehouse_app/workspace_sidebar/gudang/gudang.json
SIDEBAR_ITEMS = [
    {
        "label": "Gudang",
        "link_to": "Gudang",
        "link_type": "Workspace",
        "type": "Link",
        "icon": "package",
        "idx": 1,
    },
    {
        "label": "Handover Requests",
        "link_to": "gudang_request",
        "link_type": "Page",
        "type": "Link",
        "icon": "clipboard-list",
        "idx": 2,
    },
    {
        "label": "Serah Terima Gudang",
        "link_to": "Serah Terima Gudang",
        "link_type": "Report",
        "type": "Link",
        "icon": "truck",
        "idx": 3,
    },
    {
        "label": "Settings",
        "link_to": "gudang_settings",
        "link_type": "Page",
        "type": "Link",
        "icon": "settings",
        "idx": 4,
    },
]


def apply():
    ensure_role()
    ensure_workspace_sidebar()
    ensure_desktop_icon()


def ensure_role():
    # Site baru (mis. Frappe Cloud) belum punya role ini, padahal workspace
    # dan Page gudang di-scope ke role ini — jamin ada sejak install/migrate.
    if frappe.db.exists("Role", ROLE):
        return "unchanged"
    doc = frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1})
    doc.flags.ignore_permissions = 1
    doc.insert()
    frappe.db.commit()
    return "created"


def ensure_workspace_sidebar():
    if not frappe.db.exists("Workspace Sidebar", SIDEBAR):
        doc = frappe.get_doc(
            {
                "doctype": "Workspace Sidebar",
                "title": SIDEBAR,
                "header_icon": SIDEBAR_ICON,
                "app": APP,
                "standard": 1,
                "items": [dict(item, doctype="Workspace Sidebar Item") for item in SIDEBAR_ITEMS],
            }
        )
        doc.flags.ignore_permissions = 1
        doc.insert()
        frappe.db.commit()
        return "created"

    row = frappe.db.get_value(
        "Workspace Sidebar", SIDEBAR, ["app", "standard", "header_icon"], as_dict=1
    )
    if row and (row.app != APP or not row.standard):
        frappe.log_error(
            title="warehouse_app.upgrade",
            message=f"Workspace Sidebar {SIDEBAR!r} sudah ada tapi app={row.app!r} "
            f"standard={row.standard!r} — tidak diubah (satu pemilik data).",
        )
        return "unchanged"

    # bench migrate tidak men-sync JSON workspace_sidebar, jadi record DB yang
    # sudah ada disinkronkan di sini (tambah item/ubah icon hasil W16 dst).
    doc = frappe.get_doc("Workspace Sidebar", SIDEBAR)
    changed = []
    if row.header_icon != SIDEBAR_ICON:
        doc.header_icon = SIDEBAR_ICON
        changed.append("header_icon")
    if not _sidebar_items_match(doc.items):
        doc.set("items", [dict(item, doctype="Workspace Sidebar Item") for item in SIDEBAR_ITEMS])
        changed.append("items")
    if not changed:
        return "unchanged"
    doc.flags.ignore_permissions = 1
    doc.save()
    frappe.db.commit()
    return "synced"


def _sidebar_items_match(rows):
    current = [
        {
            "label": r.label,
            "link_to": r.link_to,
            "link_type": r.link_type,
            "type": r.type,
            "icon": r.icon or None,
            "idx": r.idx,
        }
        for r in sorted(rows, key=lambda r: r.idx or 0)
    ]
    return current == SIDEBAR_ITEMS


def ensure_desktop_icon():
    name = frappe.db.get_value("Desktop Icon", {"label": SIDEBAR}, "name")
    if name:
        row = frappe.db.get_value("Desktop Icon", name, ["link_to", "app"], as_dict=1)
        if row and (row.link_to != SIDEBAR or row.app != APP):
            frappe.log_error(
                title="warehouse_app.upgrade",
                message=f"Desktop Icon {SIDEBAR!r} sudah ada tapi link_to={row.link_to!r} "
                f"app={row.app!r} — tidak diubah (satu pemilik data).",
            )
        return "unchanged"
    doc = frappe.get_doc(
        {
            "doctype": "Desktop Icon",
            "label": SIDEBAR,
            "icon_type": "Link",
            "link_type": "Workspace Sidebar",
            "link_to": SIDEBAR,
            "icon": "package",
            "standard": 0,
            "app": APP,
        }
    )
    doc.flags.ignore_permissions = 1
    doc.insert()
    frappe.db.commit()
    return "created"
