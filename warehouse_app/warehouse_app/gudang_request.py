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
#
# Filter ala list view ERPNext (permintaan user): panel [Field][operator]
# [nilai]. Field dibatasi whitelist FILTER_FIELDS — get_list tetap
# parameterized + perm user ditegakkan, jadi tidak ada jalur injection;
# "Item" adalah field virtual yang di-expand ke production_item via
# pencarian nama/kode item (bahasa gudang adalah nama item).

import json

import frappe
from frappe.utils import flt, get_datetime

STATUS_TERBLOKIR = ("Stopped", "Closed", "Cancelled")

FILTER_FIELDS = {
	"custom_adonan_ke": {
		"label": "Batch",
		"fieldtype": "Data",
		"operators": ["=", "!="],
	},
	"creation": {
		"label": "Date",
		"fieldtype": "Date",
		"operators": ["between", ">=", "<="],
	},
	"production_item": {
		"label": "Item",
		"fieldtype": "Link",
		"operators": ["like", "="],
		"placeholder": "item name or code",
	},
	"status": {
		"label": "Work Order Status",
		"fieldtype": "Select",
		"operators": ["=", "!="],
	},
	"name": {
		"label": "Work Order No.",
		"fieldtype": "Data",
		"operators": ["like", "="],
	},
	"produced_qty": {
		"label": "Qty",
		"fieldtype": "Float",
		"operators": [">=", "<=", "="],
	},
	"fg_warehouse": {
		"label": "Finished Goods Warehouse",
		"fieldtype": "Link",
		"operators": ["like", "="],
		"placeholder": "e.g. Gudang Produksi",
	},
}


@frappe.whitelist()
def filter_fields():
	"""Meta panel filter untuk client: field + operator + opsi select."""
	meta = frappe.get_meta("Work Order")
	out = {}
	for fname, cfg in FILTER_FIELDS.items():
		entry = dict(cfg)
		df = meta.get_field(fname)
		if df and df.fieldtype == "Select":
			entry["options"] = [
				o for o in (df.options or "").split("\n") if o and not o.startswith("#")
			]
		out[fname] = entry
	return out


@frappe.whitelist()
def requestable_work_orders(search=None, filters=None):
	"""Daftar WO siap-diminta untuk user gudang: adonan + item + produced qty.

	- WO submitted, bukan Stopped/Closed/Cancelled, produced qty > 0.
	- `request_active` = ada MR aktif menempel di WO (submitted, bukan
	  Stopped, belum ada SE submitted) — semantik _active_mr_now production_app
	  tapi HANYA untuk tampilan; keputusan final tetap di endpoint
	  create_request (throw duplikat di bawah row lock).
	- `filters`: JSON list [{field, operator, value}] — field wajib ada di
	  whitelist FILTER_FIELDS; nilai kosong dilewati.
	"""
	filters_base = [
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

	for parsed_flt in _parse_filters(filters):
		filters_base.append(parsed_flt)

	rows = frappe.get_list(
		"Work Order",
		filters=filters_base,
		or_filters=or_filters,
		fields=[
			"name",
			"creation",
			"custom_adonan_ke",
			"production_item",
			"produced_qty",
			"stock_uom",
			"status",
			"fg_warehouse",
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

	# Satuan qty request mengikuti display UOM produksi (mis. Pcs -> Pack);
	# logika konversi TIDAK diduplikasi — pakai _enrich_units production_app,
	# sumber yang sama dengan validasi create_request. Fallback = stock qty.
	try:
		from production_app.api.work_order import _enrich_units

		_enrich_units(rows)
	except Exception:
		for r in rows:
			r.display_uom = r.stock_uom
			r.display_conversion_factor = 1
	for r in rows:
		factor = flt(r.get("display_conversion_factor") or 1)
		if factor <= 0:
			factor = 1
		r.expected_units = int(round(flt(r.produced_qty) / factor))
		r.display_uom = r.get("display_uom") or r.stock_uom

	return rows


def _parse_filters(filters):
	"""JSON [{field, operator, value}] -> get_list filters tervalidasi.

	Field "production_item" dicocokkan via nama/kode item (virtual); sisanya
	lolos apa adanya — get_list memakai parameter binding, perm user tetap
	ditegakkan.
	"""
	if not filters:
		return []
	try:
		parsed = json.loads(filters) if isinstance(filters, str) else filters
	except (ValueError, TypeError):
		frappe.throw(frappe._("Format filter tidak valid"))
	if not isinstance(parsed, list):
		frappe.throw(frappe._("Format filter tidak valid"))

	out = []
	for f in parsed:
		if isinstance(f, dict):
			field, operator, value = f.get("field"), f.get("operator"), f.get("value")
		else:
			field = f[0] if len(f) > 0 else None
			operator = f[1] if len(f) > 1 else None
			value = f[2] if len(f) > 2 else None
		cfg = FILTER_FIELDS.get(field)
		if not cfg or operator not in cfg["operators"]:
			frappe.throw(
				frappe._("Filter tidak didukung: {0} {1}").format(
					frappe.bold(str(field)), frappe.bold(str(operator))
				)
			)
		if value is None or str(value).strip() == "":
			continue
		if field == "production_item":
			out.extend(_item_filter(operator, str(value).strip()))
			continue
		if cfg["fieldtype"] in ("Float", "Int"):
			value = flt(value)
		if cfg["fieldtype"] == "Date":
			out.extend(_date_filter(field, operator, value))
			continue
		if operator == "like":
			# get_list "like" tidak menambah wildcard — list view ERPNext
			# juga membungkus %value% di sisi nilai.
			value = f"%{str(value).strip()}%"
		out.append([field, operator, value])
	return out


def _date_filter(field, operator, value):
	"""Filter tanggal per-hari: `creation` bertipe datetime, jadi batas
	hari diperluas ke 00:00:00–23:59:59 agar perbandingan tanggal akurat.
	Ukuran `between`: [d1, d2] (satu sisi boleh kosong -> jadi >= / <=).
	"""
	if isinstance(value, (list, tuple)):
		d1 = str(value[0] or "").strip() if len(value) > 0 else ""
		d2 = str(value[1] or "").strip() if len(value) > 1 else ""
	else:
		d1, d2 = str(value or "").strip(), ""

	if operator == "between":
		if d1 and d2:
			return [
				[field, ">=", get_datetime(d1)],
				[field, "<=", get_datetime(d2).replace(hour=23, minute=59, second=59)],
			]
		if d1:
			operator, value = ">=", d1
		elif d2:
			operator, value = "<=", d2
		else:
			return []
	elif operator in (">=", "<="):
		d1 = d1 or d2

	if not d1:
		return []
	bound = get_datetime(d1)
	if operator == "<=":
		bound = bound.replace(hour=23, minute=59, second=59)
	else:
		bound = bound.replace(hour=0, minute=0, second=0)
	return [[field, operator, bound]]


def _item_filter(operator, value):
	"""Filter Item dalam bahasa gudang: nama ATAU kode item."""
	if operator == "=":
		pat = value
		items = frappe.get_all(
			"Item",
			or_filters=[["name", "=", pat], ["item_name", "=", pat]],
			pluck="name",
			limit=0,
		)
	else:
		pat = f"%{value}%"
		items = frappe.get_all(
			"Item",
			or_filters=[["name", "like", pat], ["item_name", "like", pat]],
			pluck="name",
			limit=0,
		)
	return [["production_item", "in", items or [""]]]


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
