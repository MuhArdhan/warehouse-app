# Copyright (c) 2026, Muhammad Yusuf Tri Daryanto
# License: MIT

# Papan serah terima gudang (W3, Fase B).
# Catatan ref_doctype="Stock Entry": gerbang perm native query_report.run
# (frappe/desk/query_report.py:40-45) menuntut ptype "report" pada ref_doctype;
# Custom DocPerm Material Request (pemilik production_app, R7) men-set report=0
# utk semua role gudang, sedangkan Custom DocPerm Stock Entry ber-report=1 utk
# Stock User. Data report tetap Material Request; nol perubahan DocPerm.
# Grain: Material Request Item (MR + item docstatus 1, Material Transfer).
# Murni derivasi saat baca dari dokumen native: bucket status dari
# `per_ordered` native header MR; tanpa doc_events, tanpa tulis apa pun (R3/R10).
# Field custom production_app (`custom_work_order`, `custom_box_1/2`) dibaca
# display-only dan TIDAK PERNAH jadi filter/status (R4). Qty-only, tanpa valuasi.

import frappe
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})

	conditions = [
		"mri.docstatus = 1",
		"mr.docstatus = 1",
		"mr.material_request_type = 'Material Transfer'",
	]
	params = {}
	if filters.get("gudang_tujuan"):
		# Filter arah gudang; nama gudang tidak di-hardcode di logika (R3).
		# Kolom native MR Item utk gudang tujuan transfer = `warehouse`
		# (`t_warehouse` hanya ada di Stock Entry Detail; mapper native
		# make_stock_entry memetakan obj.warehouse -> SE.t_warehouse).
		params["warehouse"] = resolve_warehouse(filters.gudang_tujuan)
		conditions.append("mri.warehouse = %(warehouse)s")

	data = frappe.db.sql(
		f"""
		select
			mri.parent as material_request,
			mr.transaction_date as transaction_date,
			mri.custom_work_order as work_order,
			mri.item_code as item_code,
			mri.item_name as item_name,
			mri.stock_qty as qty_diminta,
			mri.ordered_qty as qty_dikirim,
			(mri.stock_qty - mri.ordered_qty) as qty_sisa,
			mri.stock_uom as stock_uom,
			mri.warehouse as gudang_tujuan,
			mr.custom_box_1 as box_1,
			mr.custom_box_2 as box_2,
			mr.per_ordered as per_ordered,
			mr.status as status_mr
		from `tabMaterial Request Item` mri
		inner join `tabMaterial Request` mr on mr.name = mri.parent
		where {" and ".join(conditions)}
		order by mr.transaction_date desc, mr.name, mri.idx
		""",
		params,
		as_dict=1,
	)

	for row in data:
		row.status_papan = get_bucket(row.per_ordered)

	return get_columns(), data


def get_columns():
	return [
		{"label": "Material Request", "fieldname": "material_request", "fieldtype": "Link", "options": "Material Request", "width": 160},
		{"label": "Tanggal", "fieldname": "transaction_date", "fieldtype": "Date", "width": 95},
		{"label": "Work Order", "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 140},
		{"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": "Qty Diminta", "fieldname": "qty_diminta", "fieldtype": "Float", "width": 110},
		{"label": "Sudah Dikirim", "fieldname": "qty_dikirim", "fieldtype": "Float", "width": 110},
		{"label": "Sisa", "fieldname": "qty_sisa", "fieldtype": "Float", "width": 90},
		{"label": "UOM", "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": "Gudang Tujuan", "fieldname": "gudang_tujuan", "fieldtype": "Link", "options": "Warehouse", "width": 170},
		{"label": "Box 1", "fieldname": "box_1", "fieldtype": "Float", "width": 90},
		{"label": "Box 2", "fieldname": "box_2", "fieldtype": "Float", "width": 90},
		{"label": "Status Papan", "fieldname": "status_papan", "fieldtype": "Data", "width": 120},
		{"label": "Status MR", "fieldname": "status_mr", "fieldtype": "Data", "width": 110},
	]


def get_bucket(per_ordered):
	"""0 -> "Belum Dikirim"; 0<per_ordered<100 -> "Sebagian"; 100 -> "Terkirim".

	`per_ordered` native header MR = qty-based percent
	(status_updater.py:606-630: sum(min(ordered_qty, stock_qty)) / sum(stock_qty) * 100),
	jadi MR 10 pcs dengan SE parsial 4 => 40.0 => "Sebagian".
	"""
	per_ordered = flt(per_ordered)
	if per_ordered <= 0:
		return "Belum Dikirim"
	if per_ordered >= 100:
		return "Terkirim"
	return "Sebagian"


def resolve_warehouse(name):
	"""Resolve nama filter ke warehouse eksak; izinkan akhiran abbr situs.

	Default filter "Gudang Barang Jadi" tetap valid di situs ber-abbr (mis.
	"Gudang Barang Jadi - ROPI"): exact match dulu, kalau tidak ada, cari
	satu warehouse non-group berawalan `<nama> -`. Tanpa nama gudang yang
	di-hardcode (R3).
	"""
	if frappe.db.exists("Warehouse", name):
		return name
	match = frappe.db.get_value(
		"Warehouse",
		{"name": ("like", f"{name} -%"), "is_group": 0},
		"name",
		order_by="name",
	)
	if not match:
		frappe.throw(frappe._("Warehouse {0} tidak ditemukan").format(frappe.bold(name)))
	return match
