# W11: pengaturan gudang serah terima — UI tipis di atas dua field
# Manufacturing Settings milik production_app:
#   custom_default_handover_source_warehouse (kosong = ikut lot produksi)
#   custom_default_handover_warehouse        (gudang tujuan, wajib saat create)
# production_app tetap satu penulis alur serah terima (R11): page ini hanya
# membaca/menulis NILAI setting-nya; endpoint & validasi di sana tak disentuh.

import frappe

SETTING_FIELDS = {
	"source": "custom_default_handover_source_warehouse",
	"target": "custom_default_handover_warehouse",
}
ROLES_SET = ("System Manager", "Gudang Barang Jadi")


def _require_set_access():
	if not any(role in frappe.get_roles() for role in ROLES_SET):
		frappe.throw(
			frappe._("Hanya System Manager atau Gudang Barang Jadi yang dapat mengubah pengaturan."),
			frappe.PermissionError,
		)


def _clean_warehouse(value, label):
	"""Kosong berarti 'tidak diatur'; selain itu harus Warehouse non-group."""
	value = (value or "").strip()
	if not value:
		return None
	if not frappe.db.exists("Warehouse", value) or frappe.db.get_value(
		"Warehouse", value, "is_group"
	):
		frappe.throw(frappe._("{0} bukan gudang yang valid.").format(label))
	return value


@frappe.whitelist()
def get_handover_settings():
	return {
		"source": frappe.db.get_single_value("Manufacturing Settings", SETTING_FIELDS["source"])
		or "",
		"target": frappe.db.get_single_value("Manufacturing Settings", SETTING_FIELDS["target"])
		or "",
	}


@frappe.whitelist()
def warehouse_options():
	"""Daftar gudang non-group aktif untuk dropdown settings."""
	return frappe.get_all(
		"Warehouse",
		filters={"is_group": 0, "disabled": 0},
		fields=["name"],
		order_by="name",
		pluck="name",
		limit=0,
	)


@frappe.whitelist()
def set_handover_warehouses(source=None, target=None):
	_require_set_access()
	source = _clean_warehouse(source, "Source Warehouse")
	target = _clean_warehouse(target, "Target Warehouse")
	frappe.db.set_single_value("Manufacturing Settings", SETTING_FIELDS["source"], source)
	frappe.db.set_single_value("Manufacturing Settings", SETTING_FIELDS["target"], target)
	frappe.db.commit()
	return {"ok": True, "source": source or "", "target": target or ""}

