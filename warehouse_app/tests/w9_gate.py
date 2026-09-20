# Copyright (c) 2026, Muhammad Yusuf Tri Daryanto
# License: MIT

# Gate W9 — request serah terima ala-gudang (adonan + item).
#
# Jalankan:
#   docker exec erpnext-new-backend-1 bench --site frontend execute \
#       warehouse_app.tests.w9_gate.run_gate
#
# Kontrak output: TEPAT satu baris GATE_JSON:{...} (ok: bool, checks: dict,
# error: opsional). Cek gagal -> ok=false TANPA raise; hanya crash tak terduga
# yang di-raise (bench exit nonzero).
#
# Yang diverifikasi (ruling W9 Opsi A — UI tipis memanggil endpoint
# production_app; warehouse_app hanya picker read-only):
#   1. Picker warehouse_app (requestable_work_orders) sebagai fixture user
#      role gudang: WO fixture tampil dengan adonan + item_name;
#      request_active mengikuti state MR.
#   2. create_request production_app (pemanggilan = kontrak yang dijaga):
#      MR submitted Material Transfer + row custom_work_order + ringkasan WO
#      terisi; papan Serah Terima menampilkan MR tsb dengan kolom Adonan.
#   3. Guard duplikat production_app menolak request kedua.
#   4. cancel_request membatalkan MR + membersihkan ringkasan WO.
#   5. Negative: user tanpa role ditolak di picker (perm WO) dan di
#      create_request (role gate production_app).
#
# Fixture (prefix "ZZTEST-W9"): Item stok tanpa batch, WO (ignore_validate,
# docstatus dinaikkan manual), SE Manufacture (lot batchless production_app).
# MR/SE/WO hasil endpoint memakai naming series native (MAT-*/MFG-*) — tidak
# ber-prefix, jadi teardown melacak via item (SED/MRI/production_item) +
# daftar nama yang tercipta saat run. Teardown lengkap di finally.

import json
import traceback

import frappe
from frappe.utils import flt

from warehouse_app.tests.guard import count_residue
from warehouse_app.warehouse_app.gudang_request import requestable_work_orders
from warehouse_app.warehouse_app.report.serah_terima_gudang.serah_terima_gudang import (
	execute as run_report,
	resolve_warehouse,
)

PREFIX = "ZZTEST-W9"
ITEM_CODE = PREFIX + "-ITEM"
ITEM_NAME = "ZZTEST W9 Gate Item"  # varian ber-spasi: cakupan guard item_name
USER_EMAIL = PREFIX + "@example.com"
ADONAN = "W9"
QTY = 100

# Dokumen bernama native (tidak ber-prefix) yang tercipta saat run.
TRACKED = {"wo": [], "se": [], "mr": [], "item": []}


class GateAborted(Exception):
	"""Prasyarat gate gagal; sisa langkah dilewati, GATE_JSON tetap dicetak (ok=false)."""


def run_gate():
	checks = {}
	error = None

	def check(name, ok, evidence):
		checks[name] = str(evidence) if ok else f"GAGAL: {evidence}"

	try:
		_run_gate(check)
	except GateAborted:
		pass
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

	# --- Preflight ---
	target = _safe_resolve("Gudang Barang Jadi")
	source = _safe_resolve("Gudang Produksi")
	company = frappe.db.get_value("Warehouse", target, "company") if target else None
	setting_target = frappe.db.get_single_value(
		"Manufacturing Settings", "custom_default_handover_warehouse"
	)
	check(
		"preflight",
		bool(target and source and company and setting_target == target),
		f"source={source!r}, target={target!r}, setting={setting_target!r}",
	)
	if not (target and source and company):
		raise GateAborted()

	uom = next((u for u in ("Nos", "Kg") if frappe.db.exists("UOM", u)), None)
	item_group = _pick_item_group()
	check("preflight_uom_group", bool(uom and item_group), f"uom={uom!r}, group={item_group!r}")
	if not (uom and item_group):
		raise GateAborted()

	# --- Item fixture (tanpa batch -> lot batchless production_app) ---
	try:
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": ITEM_CODE,
				"item_name": ITEM_NAME,
				"item_group": item_group,
				"stock_uom": uom,
				"is_stock_item": 1,
				"has_batch_no": 0,
				"has_serial_no": 0,
			}
		)
		item.insert()
		# Naming series site menimpa name/item_code -> rename agar ber-prefix.
		if not item.name.startswith(PREFIX):
			frappe.rename_doc("Item", item.name, ITEM_CODE)
		TRACKED["item"].append(ITEM_CODE)
		check("fixture_item", frappe.db.exists("Item", ITEM_CODE) is not None, ITEM_CODE)
	except Exception as e:
		check("fixture_item", False, f"{type(e).__name__}: {e}")
		raise GateAborted()

	# --- WO fixture: ignore_validate + docstatus manual (pola probe) ---
	try:
		wo = frappe.get_doc(
			{
				"doctype": "Work Order",
				"company": company,
				"production_item": ITEM_CODE,
				"qty": QTY,
				"stock_uom": uom,
				"fg_warehouse": source,
				"wip_warehouse": source,
				"custom_adonan_ke": ADONAN,
			}
		)
		wo.flags.ignore_validate = True
		wo.flags.ignore_mandatory = True
		wo.insert(ignore_permissions=True)
		frappe.db.set_value(
			"Work Order",
			wo.name,
			{"docstatus": 1, "status": "Completed", "produced_qty": QTY},
			update_modified=False,
		)
		TRACKED["wo"].append(wo.name)
		check(
			"fixture_wo",
			frappe.db.get_value("Work Order", wo.name, ["docstatus", "produced_qty", "custom_adonan_ke"], as_dict=1).docstatus == 1,
			f"{wo.name} adonan={ADONAN} produced={QTY} {uom}",
		)
	except Exception as e:
		check("fixture_wo", False, f"{type(e).__name__}: {e}")
		raise GateAborted()

	# --- SE Manufacture: sumber lot production_app ---
	try:
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"company": company,
				"purpose": "Manufacture",
				"work_order": wo.name,
				"items": [
					{
						"item_code": ITEM_CODE,
						"t_warehouse": source,
						"qty": QTY,
						"transfer_qty": QTY,
						"stock_uom": uom,
						"conversion_factor": 1,
						"is_finished_item": 1,
						"expense_account": frappe.db.get_value("Company", company, "default_expense_account"),
						"cost_center": frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name"),
					}
				],
			}
		)
		se.flags.ignore_validate = True
		se.flags.ignore_mandatory = True
		se.submit()
		TRACKED["se"].append(se.name)
		check("fixture_se_manufacture", se.docstatus == 1, f"{se.name}: {QTY} {uom} -> {source}")
	except Exception as e:
		check("fixture_se_manufacture", False, f"{type(e).__name__}: {e}")
		raise GateAborted()

	# --- User fixture: TANPA role dulu -> negative checks ---
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
		check("fixture_user", frappe.db.exists("User", USER_EMAIL) is not None, USER_EMAIL)
	except Exception as e:
		check("fixture_user", False, f"{type(e).__name__}: {e}")
		raise GateAborted()

	frappe.set_user(USER_EMAIL)
	try:
		requestable_work_orders()
		check("picker_denied_without_role", False, "requestable_work_orders TIDAK ditolak untuk user tanpa role")
	except frappe.PermissionError as e:
		check("picker_denied_without_role", True, f"PermissionError: {str(e)[:150]}")
	except Exception as e:
		check("picker_denied_without_role", False, f"{type(e).__name__}: {str(e)[:150]}")
	finally:
		frappe.set_user("Administrator")

	try:
		from production_app.api.handover import create_request

		frappe.set_user(USER_EMAIL)
		try:
			create_request(work_order=TRACKED["wo"][0], box_1=50, box_1_qty=QTY, box_2=0, box_2_qty=0)
			check("create_denied_without_role", False, "create_request TIDAK ditolak untuk user tanpa role")
		finally:
			frappe.set_user("Administrator")
	except frappe.PermissionError as e:
		check("create_denied_without_role", True, f"PermissionError: {str(e)[:150]}")
	except Exception as e:
		msg = str(e)
		ok = "peran gudang" in msg
		check("create_denied_without_role", ok, f"{type(e).__name__}: {msg[:150]}")

	# --- Beri role gudang ---
	try:
		user = frappe.get_doc("User", USER_EMAIL)
		user.add_roles("Gudang Barang Jadi", "Stock User")
		frappe.clear_cache(user=USER_EMAIL)
		check("fixture_roles", "Gudang Barang Jadi" in frappe.get_roles(USER_EMAIL), str(frappe.get_roles(USER_EMAIL)))
	except Exception as e:
		check("fixture_roles", False, f"{type(e).__name__}: {e}")
		raise GateAborted()

	from production_app.api.handover import cancel_request, create_request

	# --- Picker: WO fixture tampil, search, dan request_active=False ---
	try:
		frappe.set_user(USER_EMAIL)
		rows = requestable_work_orders()
		row = next((r for r in rows if r.name == TRACKED["wo"][0]), None)
		ok = bool(
			row
			and row.custom_adonan_ke == ADONAN
			and row.item_name == ITEM_NAME
			and not row.request_active
		)
		check("picker_lists_wo", ok, f"wo={row and row.name}, adonan={row and row.custom_adonan_ke!r}, item={row and row.item_name!r}, active={row and row.request_active}")

		found = [r.name for r in requestable_work_orders(search="ZZTEST W9 Gate") if r.name == TRACKED["wo"][0]]
		none_found = requestable_work_orders(search="ZZTEST-W9-TIDAK-ADE")

		def _wo_in(rs):
			return any(r.name == TRACKED["wo"][0] for r in rs)

		check(
			"picker_search",
			len(found) == 1 and not _wo_in(none_found),
			f"search cocok={len(found)}, search bogus menemukan fixture={_wo_in(none_found)}",
		)

		# --- Filter ala list view (whitelist server) ---
		res_filter = requestable_work_orders(
			filters=json.dumps([{"field": "custom_adonan_ke", "operator": "=", "value": ADONAN}])
		)
		res_item = requestable_work_orders(
			filters=json.dumps([{"field": "production_item", "operator": "like", "value": "ZZTEST W9"}])
		)
		res_bogus = requestable_work_orders(
			filters=json.dumps([{"field": "custom_adonan_ke", "operator": "=", "value": "TIDAK-ADA-99"}])
		)
		check(
			"picker_filter",
			_wo_in(res_filter) and _wo_in(res_item) and not _wo_in(res_bogus),
			f"filter adonan cocok={_wo_in(res_filter)}, filter item cocok={_wo_in(res_item)}, nilai bogus kosong={not _wo_in(res_bogus)}",
		)
		try:
			requestable_work_orders(
				filters=json.dumps([{"field": "bogus_field", "operator": "=", "value": "x"}])
			)
			check("picker_filter_whitelist", False, "field di luar whitelist TIDAK ditolak!")
		except frappe.ValidationError as e:
			check("picker_filter_whitelist", True, f"ValidationError: {str(e)[:120]}")
	except Exception as e:
		check("picker_lists_wo", False, f"{type(e).__name__}: {e}")
		frappe.set_user("Administrator")
		raise GateAborted()

	# --- create_request sebagai user gudang ---
	try:
		res = create_request(work_order=TRACKED["wo"][0], box_1=50, box_1_qty=QTY, box_2=0, box_2_qty=0)
		mr_name = res["material_request"]
		TRACKED["mr"].append(mr_name)
		mr = frappe.db.get_value(
			"Material Request", mr_name, ["docstatus", "material_request_type", "set_from_warehouse", "set_warehouse"], as_dict=1
		)
		mri = frappe.db.get_value(
			"Material Request Item", {"parent": mr_name}, ["item_code", "qty", "custom_work_order", "warehouse"], as_dict=1
		)
		ok = bool(
			res.get("ok")
			and mr.docstatus == 1
			and mr.material_request_type == "Material Transfer"
			and mr.set_from_warehouse == source
			and mr.set_warehouse == target
			and mri.item_code == ITEM_CODE
			and flt(mri.qty) == QTY
			and mri.custom_work_order == TRACKED["wo"][0]
			and mri.warehouse == target
		)
		check("create_request", ok, f"{mr_name}: {mr}, {mri}")
	except Exception as e:
		check("create_request", False, f"{type(e).__name__}: {e}")
		frappe.set_user("Administrator")
		raise GateAborted()

	# --- Ringkasan WO terisi + picker request_active=True ---
	try:
		summary = frappe.db.get_value(
			"Work Order", TRACKED["wo"][0], ["custom_handover_material_request", "custom_box_1", "custom_box_1_qty"], as_dict=1
		)
		check(
			"wo_summary_filled",
			summary.custom_handover_material_request == TRACKED["mr"][0] and flt(summary.custom_box_1) == 50 and flt(summary.custom_box_1_qty) == QTY,
			str(summary),
		)
		rows = requestable_work_orders(search=ITEM_NAME)
		row = next((r for r in rows if r.name == TRACKED["wo"][0]), None)
		check("picker_active_flag", bool(row and row.request_active), f"request_active={row and row.request_active}")
	except Exception as e:
		check("wo_summary_filled", False, f"{type(e).__name__}: {e}")

	# --- Guard duplikat production_app ---
	try:
		create_request(work_order=TRACKED["wo"][0], box_1=50, box_1_qty=QTY, box_2=0, box_2_qty=0)
		check("duplicate_rejected", False, "create_request kedua TIDAK ditolak!")
	except Exception as e:
		msg = str(e)
		check("duplicate_rejected", "sudah punya permintaan aktif" in msg, f"{type(e).__name__}: {msg[:180]}")

	# --- Papan: MR fixture muncul dengan kolom Adonan, bucket Belum Dikirim ---
	try:
		columns, rows = run_report({"gudang_tujuan": target})
		fieldnames = [c.get("fieldname") for c in columns]
		brow = next((r for r in rows if r.get("material_request") == TRACKED["mr"][0]), None)
		ok = bool(
			brow
			and brow.get("adonan") == ADONAN
			and brow.get("status_papan") == "Belum Dikirim"
			and "adonan" in fieldnames
			and fieldnames.index("adonan") < fieldnames.index("work_order")
		)
		check("board_shows_request", ok, f"row={brow and dict(brow)}, adonan@kolom-{fieldnames.index('adonan') if 'adonan' in fieldnames else '?'}")
	except Exception as e:
		check("board_shows_request", False, f"{type(e).__name__}: {e}")

	# --- cancel_request: MR batal + ringkasan WO bersih + picker normal lagi ---
	try:
		cancel_request(material_request=TRACKED["mr"][0])
		mr_after = frappe.db.get_value("Material Request", TRACKED["mr"][0], ["docstatus", "status"], as_dict=1)
		summary_after = frappe.db.get_value("Work Order", TRACKED["wo"][0], "custom_handover_material_request")
		rows = requestable_work_orders(search=ITEM_NAME)
		row = next((r for r in rows if r.name == TRACKED["wo"][0]), None)
		ok = bool(
			mr_after.docstatus == 2
			and mr_after.status == "Cancelled"
			and summary_after in (None, "")
			and row
			and not row.request_active
		)
		check("cancel_request", ok, f"mr={dict(mr_after)}, wo_link={summary_after!r}, active={row and row.request_active}")
	except Exception as e:
		check("cancel_request", False, f"{type(e).__name__}: {e}")
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
	check(
		"teardown",
		sweep_ok and zero,
		f"{sweep_evidence}; residu {PREFIX}={residue}",
	)


def _sweep():
	"""Bersihkan residu W9: via item prefix + nama native yang ter-track. Idempoten."""
	errors = []

	def safe(label, fn):
		try:
			fn()
		except Exception as e:
			errors.append(f"{label}: {type(e).__name__}: {str(e)[:120]}")

	def cancel_delete(doctype, name):
		if not frappe.db.exists(doctype, name):
			return
		doc = frappe.get_doc(doctype, name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc(doctype, name, force=1, ignore_missing=True)

	items = frappe.get_all(
		"Item",
		or_filters=[
			["Item", "name", "like", PREFIX + "%"],
			["Item", "item_code", "like", PREFIX + "%"],
			["Item", "item_name", "like", PREFIX + "%"],
			["Item", "item_name", "like", PREFIX.replace("-", " ") + "%"],
		],
		pluck="name",
	)
	# SE via row item (native naming MAT-*) atau track list
	se_names = set(TRACKED["se"])
	if items:
		se_names.update(
			frappe.get_all("Stock Entry Detail", filters={"item_code": ("in", items)}, pluck="parent")
		)
	for name in se_names:
		safe(f"SE {name}", lambda n=name: cancel_delete("Stock Entry", n))
	# MR via row item atau track list
	mr_names = set(TRACKED["mr"])
	if items:
		mr_names.update(
			frappe.get_all("Material Request Item", filters={"item_code": ("in", items)}, pluck="parent")
		)
	for name in mr_names:
		safe(f"MR {name}", lambda n=name: cancel_delete("Material Request", n))
	# WO via production_item atau track list (hapus SETELAH SE/MR). WO fixture
	# docstatus dinaikkan manual: turunkan dulu, karena submitted record
	# tidak bisa di-force-delete.
	wo_names = set(TRACKED["wo"])
	if items:
		wo_names.update(frappe.get_all("Work Order", filters={"production_item": ("in", items)}, pluck="name"))
	for name in wo_names:
		def del_wo(n=name):
			frappe.db.set_value("Work Order", n, "docstatus", 0, update_modified=False)
			frappe.delete_doc("Work Order", n, force=1, ignore_missing=True)
		safe(f"WO {name}", del_wo)
	# SLE/Bin/Repost per item (jaga-jaga bila cancel SE tak sempat membersihkan)
	safe("SLE", lambda: frappe.db.delete("Stock Ledger Entry", {"item_code": ("in", items or [""])}) if items else None)
	safe("Repost", lambda: frappe.db.delete("Repost Item Valuation", {"item_code": ("in", items or [""])}) if items else None)
	safe("Bin", lambda: frappe.db.delete("Bin", {"item_code": ("in", items or [""])}) if items else None)
	# Item
	for name in items:
		safe(f"Item {name}", lambda n=name: frappe.delete_doc("Item", n, force=1, ignore_missing=True))
	# User + jejak sesi
	for name in frappe.get_all("User", filters={"name": ("like", PREFIX + "%")}, pluck="name"):
		safe(f"User {name}", lambda n=name: frappe.delete_doc("User", n, force=1, ignore_missing=True))
	safe("Sessions", lambda: frappe.db.delete("Sessions", {"user": ("like", PREFIX + "%")}))
	safe("ActivityLog.user", lambda: frappe.db.delete("Activity Log", {"user": ("like", PREFIX + "%")}))
	if frappe.db.has_column("Activity Log", "for_user"):
		safe("ActivityLog.for_user", lambda: frappe.db.delete("Activity Log", {"for_user": ("like", PREFIX + "%")}))
	safe("Version", lambda: frappe.db.delete("Version", {"docname": ("like", PREFIX + "%")}))

	TRACKED.update({"wo": [], "se": [], "mr": [], "item": []})
	return (not errors), ("bersih" if not errors else "; ".join(errors[:5]))


def _safe_resolve(base):
	try:
		return resolve_warehouse(base)
	except Exception:
		return None


def _pick_item_group():
	for group in ("Bread", "Products"):
		if frappe.db.exists("Item Group", group) and not frappe.db.get_value("Item Group", group, "is_group"):
			return group
	return frappe.db.get_value("Item Group", {"is_group": 0}, "name", order_by="name")
