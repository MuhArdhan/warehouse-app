# Copyright (c) 2026, Muhammad Yusuf Tri Daryanto
# License: MIT

# Picker request serah terima ala-gudang (W9).
# Bahasa gudang: adonan ke + nama item — bukan nomor WO + qty.
# Endpoint ini HANYA membaca Work Order untuk daftar; pembuatan/pembatalan
# MR tetap lewat endpoint production_app (create_request/cancel_request)
# yang dipanggil client langsung — production_app tetap satu-satunya penulis
# ringkasan WO (custom_handover_material_request + box), nol duplikasi logika
# (ruling W9 Opsi A). Gudang punya read Work Order (Stock User / Gudang
# Barang Jadi), jadi get_list polos tanpa bypass perm.

import frappe

STATUS_TERBLOKIR = ("Stopped", "Closed", "Cancelled")


@frappe.whitelist()
def requestable_work_orders(search=None):
	"""Daftar WO siap-diminta untuk user gudang: adonan + item + produced qty.

	- WO submitted, bukan Stopped/Closed/Cancelled, produced qty > 0.
	- `request_active` = ada MR aktif menempel di WO (submitted, bukan
	  Stopped, belum ada SE submitted) — semantik _active_mr_now production_app
	  tapi HANYA untuk tampilan; keputusan final tetap di endpoint
	  create_request (throw duplikat di bawah row lock).
	"""
	filters = [
		["docstatus", "=", 1],
		["status", "not in", list(STATUS_TERBLOKIR)],
		["produced_qty", ">", 0],
	]
	or_filters = None
	search = str(search or "").strip()
	if search:
		pattern = f"%{search}%"
		items = frappe.get_all(
			"Item", filters=[["item_name", "like", pattern]], pluck="name", limit=0
		)
		or_filters = [
			["custom_adonan_ke", "like", pattern],
			["name", "like", pattern],
			["production_item", "in", items or [""]],
		]

	rows = frappe.get_list(
		"Work Order",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"custom_adonan_ke",
			"production_item",
			"produced_qty",
			"stock_uom",
			"status",
			"custom_handover_material_request",
		],
		order_by="creation desc",
		limit_page_length=50,
	)

	item_names = dict(
		frappe.get_all(
			"Item",
			filters=[["name", "in", [r.production_item for r in rows] or [""]]],
			fields=["name", "item_name"],
			as_list=True,
		)
	)
	mr_info, mr_dikirim = _active_request_map(rows)

	for r in rows:
		r.item_name = item_names.get(r.production_item) or r.production_item
		mr = r.custom_handover_material_request
		docstatus, status = mr_info.get(mr, (None, None))
		r.request_active = bool(
			mr and docstatus == 1 and status != "Stopped" and mr not in mr_dikirim
		)

	return rows


def _active_request_map(rows):
	"""(docstatus, status) per MR + set MR yang sudah ada SE submitted."""
	mr_names = [
		r.custom_handover_material_request for r in rows if r.custom_handover_material_request
	]
	if not mr_names:
		return {}, set()
	mr_info = {
		name: (docstatus, status)
		for name, docstatus, status in frappe.get_all(
			"Material Request",
			filters=[["name", "in", mr_names]],
			fields=["name", "docstatus", "status"],
			as_list=True,
		)
	}
	mr_dikirim = set(
		frappe.get_all(
			"Stock Entry Detail",
			filters={
				"material_request": ("in", mr_names),
				"docstatus": 1,
				"parenttype": "Stock Entry",
			},
			pluck="material_request",
		)
	)
	return mr_info, mr_dikirim
