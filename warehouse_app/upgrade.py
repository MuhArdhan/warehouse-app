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


def apply():
    ensure_workspace_sidebar()
    ensure_desktop_icon()


def ensure_workspace_sidebar():
    if frappe.db.exists("Workspace Sidebar", SIDEBAR):
        row = frappe.db.get_value("Workspace Sidebar", SIDEBAR, ["app", "standard"], as_dict=1)
        if row and (row.app != APP or not row.standard):
            frappe.log_error(
                title="warehouse_app.upgrade",
                message=f"Workspace Sidebar {SIDEBAR!r} sudah ada tapi app={row.app!r} "
                f"standard={row.standard!r} — tidak diubah (satu pemilik data).",
            )
        return "unchanged"
    doc = frappe.get_doc(
        {
            "doctype": "Workspace Sidebar",
            "title": SIDEBAR,
            "app": APP,
            "standard": 1,
            "items": [
                {
                    "doctype": "Workspace Sidebar Item",
                    "label": SIDEBAR,
                    "link_to": SIDEBAR,
                    "link_type": "Workspace",
                    "type": "Link",
                    "idx": 1,
                }
            ],
        }
    )
    doc.flags.ignore_permissions = 1
    doc.insert()
    frappe.db.commit()
    return "created"


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
