# Copyright (c) 2026, Muhammad Yusuf Tri Daryanto
# License: MIT

# Gate W3 — verifikasi eksekusi Script Report "Serah Terima Gudang" (Fase B).
#
# Jalankan:
#   docker exec erpnext-new-backend-1 bench --site frontend execute \
#       warehouse_app.tests.w3_gate.run_gate
#
# Kontrak output: TEPAT satu baris GATE_JSON:{...} (ok: bool, checks: dict,
# error: opsional). Cek gagal -> ok=false TANPA raise; hanya crash tak terduga
# yang di-raise (bench exit nonzero; transaksi di-rollback oleh frappe.destroy).
#
# Fixture (prefix "ZZTEST-W3"): Item stok has_batch_no=1/create_new_batch=1,
# SE Material Receipt ke gudang sumber, tiga MR Material Transfer ke
# "Gudang Barang Jadi" (penuh 10/10, parsial 4/10, 10/10 belum dikirim).
# Teardown lengkap di finally: SE -> MR -> Serial and Batch Bundle -> Batch ->
# Bin -> Item -> User fixture + Sessions/Activity Log/Version-nya.
# Tanpa custom field baru, tanpa doc_events; semua lewat API native.

import json
import traceback

import frappe
from erpnext.stock.doctype.material_request.material_request import make_stock_entry
from frappe.utils import flt, nowdate

from warehouse_app.tests.guard import count_residue
from warehouse_app.warehouse_app.report.serah_terima_gudang.serah_terima_gudang import (
	execute as run_report,
	resolve_warehouse,
)

PREFIX = "ZZTEST-W3"
REPORT_NAME = "Serah Terima Gudang"
ITEM_CODE = PREFIX + "-ITEM"
USER_EMAIL = PREFIX + "@example.com"  # nama User Frappe = email, harus valid
SE_SERIES = PREFIX + "-SE-.#####"
MR_SERIES = PREFIX + "-MR-.#####"
BATCH_SERIES = PREFIX + "-B-.#####"
OVERQTY_FRAGMENT = "cannot be greater than requested quantity"

TARGET_BASE = "Gudang Barang Jadi"
SOURCE_BASES = ("Gudang Produksi", "Gudang Bahan Baku")


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
		# Crash tak terduga -> raise agar bench execute exit nonzero.
		raise SystemExit(1)


def _run_gate(check):
	check("pre_clean", *_sweep())

	# --- Preflight: gudang yang benar-benar ada di situs ---
	target = _safe_resolve(TARGET_BASE)
	source = next((w for w in (_safe_resolve(b) for b in SOURCE_BASES) if w), None)
	company = frappe.db.get_value("Warehouse", target, "company") if target else None
	check(
		"preflight_gudang",
		bool(target and source and company),
		f"source={source!r}, target={target!r}, company={company!r}",
	)
	if not (target and source and company):
		raise GateAborted()

	uom = next((u for u in ("Kg", "Nos") if frappe.db.exists("UOM", u)), None)
	item_group = _pick_item_group()
	check(
		"preflight_uom_group",
		bool(uom and item_group),
		f"uom={uom!r}, item_group={item_group!r}",
	)
	if not (uom and item_group):
		raise GateAborted()

	# --- Item fixture: stok + batch otomatis ---
	try:
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": ITEM_CODE,
				"item_name": "ZZTEST W3 Gate Item",
				"item_group": item_group,
				"stock_uom": uom,
				"is_stock_item": 1,
				"has_batch_no": 1,
				"create_new_batch": 1,
				"batch_number_series": BATCH_SERIES,
			}
		)
		item.insert()
		# Situs ini memakai "Item Naming By = Naming Series" sehingga Item.autoname
		# menimpa name & item_code dengan ITEM-#####  -> rename agar tetap ber-prefix
		# ZZTEST-W3 (dapat ditrack guard/sweep). Belum punya link apapun saat ini.
		frappe.rename_doc("Item", item.name, ITEM_CODE)
		check(
			"fixture_item",
			frappe.db.get_value(
				"Item", ITEM_CODE, ["has_batch_no", "create_new_batch"], as_dict=1
			).create_new_batch
			== 1,
			f"{ITEM_CODE} has_batch_no=1 create_new_batch=1 series={BATCH_SERIES} uom={uom}",
		)
	except Exception as e:
		check("fixture_item", False, f"{type(e).__name__}: {e}")
		raise GateAborted()

	try:
		# pakai ITEM_CODE (bukan item.name yang basi pasca-rename)
		batch = frappe.get_doc({"doctype": "Batch", "item": ITEM_CODE}).insert()
		check("fixture_batch", batch.name.startswith(PREFIX), f"Batch {batch.name}")
	except Exception as e:
		check("fixture_batch", False, f"{type(e).__name__}: {e}")
		raise GateAborted()

	# --- SE Material Receipt 40 ke gudang sumber (biar transfer ke target punya stok) ---
	try:
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"naming_series": SE_SERIES,
				"company": company,
				"items": [
					{
						"item_code": ITEM_CODE,
						"qty": 40,
						"t_warehouse": source,
						"use_serial_batch_fields": 1,
						"batch_no": batch.name,
						"basic_rate": 100,
					}
				],
			}
		)
		receipt.insert()
		receipt.submit()
		check(
			"receipt_submitted",
			receipt.docstatus == 1,
			f"{receipt.name}: 40 {uom} (batch {batch.name}) -> {source}",
		)
	except Exception as e:
		check("receipt_submitted", False, f"{type(e).__name__}: {e}")
		raise GateAborted()

	# --- Tiga MR Material Transfer: penuh 10/10, parsial 10 (nanti 4), kosong 10 ---
	mr_names = {}
	mr_errors = []
	for key in ("full", "partial", "unsent"):
		try:
			mr = frappe.get_doc(
				{
					"doctype": "Material Request",
					"naming_series": MR_SERIES,
					"material_request_type": "Material Transfer",
					"company": company,
					"transaction_date": nowdate(),
					"items": [
						{
							"item_code": ITEM_CODE,
							"qty": 10,
							"uom": uom,
							"warehouse": target,
							"t_warehouse": target,
							"from_warehouse": source,
							"schedule_date": nowdate(),
						}
					],
				}
			)
			mr.insert()
			mr.submit()
			mr_names[key] = mr.name
		except Exception as e:
			mr_errors.append(f"{key}: {type(e).__name__}: {e}")
	check("mr_created", len(mr_names) == 3, f"{mr_names} | errors={mr_errors}")
	if len(mr_names) != 3:
		raise GateAborted()

	# --- Mapper native + submit SE penuh: 10/10 -> per_ordered 100 ---
	def mapped_se(mr_name):
		se = make_stock_entry(mr_name)  # SE draft dari mapper native (qty = sisa)
		se.naming_series = SE_SERIES
		row = se.items[0]
		row.use_serial_batch_fields = 1
		row.batch_no = batch.name
		return se, row

	try:
		se_full, row = mapped_se(mr_names["full"])
		check("mapper_sisa_full", flt(row.qty) == 10, f"SE draft qty={flt(row.qty)} (sisa=10)")
		se_full.insert()
		se_full.submit()
		po_full = flt(frappe.db.get_value("Material Request", mr_names["full"], "per_ordered"))
		check("full_delivered", po_full == 100, f"{se_full.name} submit; per_ordered={po_full}")
	except Exception as e:
		check("full_delivered", False, f"{type(e).__name__}: {e}")

	# --- SE parsial: mapper 10 -> dipangkas 4 -> per_ordered 40 ---
	try:
		se_part, row = mapped_se(mr_names["partial"])
		check("mapper_sisa_partial", flt(row.qty) == 10, f"SE draft qty={flt(row.qty)} (sisa=10)")
		row.qty = 4
		row.transfer_qty = flt(row.qty) * flt(row.conversion_factor)
		se_part.insert()
		se_part.submit()
		po_part = flt(frappe.db.get_value("Material Request", mr_names["partial"], "per_ordered"))
		check("partial_delivered", po_part == 40, f"{se_part.name} qty=4 submit; per_ordered={po_part}")
	except Exception as e:
		check("partial_delivered", False, f"{type(e).__name__}: {e}")

	# --- Over-qty: mapper (sisa 6) dinaikkan ke 7 -> submit HARUS ditolak native ---
	try:
		se_over, row = mapped_se(mr_names["partial"])
		check("mapper_sisa_after_partial", flt(row.qty) == 6, f"SE draft qty={flt(row.qty)} (sisa=6)")
		row.qty = 7
		row.transfer_qty = flt(row.qty) * flt(row.conversion_factor)
		se_over.insert()
		try:
			se_over.submit()
			check("overqty_rejected", False, "submit SE over-qty (7 saat sisa 6) TIDAK ditolak!")
		except Exception as e:
			msg = str(e)
			check("overqty_rejected", OVERQTY_FRAGMENT in msg, f"{type(e).__name__}: {msg[:220]}")
	except Exception as e:
		check("overqty_rejected", False, f"draft gagal dibuat: {type(e).__name__}: {e}")

	# --- Bucket report via execute langsung ---
	try:
		columns, rows = run_report({"gudang_tujuan": target})
		buckets = {r.get("material_request"): r.get("status_papan") for r in rows}
		check(
			"report_bucket_full",
			buckets.get(mr_names["full"]) == "Terkirim",
			f"full={buckets.get(mr_names['full'])!r} (harap 'Terkirim')",
		)
		check(
			"report_bucket_partial",
			buckets.get(mr_names["partial"]) == "Sebagian",
			f"partial={buckets.get(mr_names['partial'])!r} (harap 'Sebagian')",
		)
		check(
			"report_bucket_unsent",
			buckets.get(mr_names["unsent"]) == "Belum Dikirim",
			f"unsent={buckets.get(mr_names['unsent'])!r} (harap 'Belum Dikirim')",
		)
		forbidden = {"valuation_rate", "rate", "amount", "basic_rate", "basic_amount", "stock_value", "stock_value_difference", "price_list_rate"}
		found_forbidden = sorted(forbidden & {c.get("fieldname") for c in columns})
		check("no_valuation_columns", not found_forbidden, f"{len(columns)} kolom qty-only; terlarang={found_forbidden}")
		check(
			"default_filter_resolves",
			resolve_warehouse(TARGET_BASE) == target,
			f"filter default {TARGET_BASE!r} -> {resolve_warehouse(TARGET_BASE)!r}",
		)
	except Exception as e:
		check("report_bucket_full", False, f"{type(e).__name__}: {e}")

	# --- User fixture: tanpa role -> ditolak; dengan 2 role -> lulus ---
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
		check(
			"fixture_user",
			frappe.db.exists("User", USER_EMAIL) is not None,
			f"{USER_EMAIL} System User, desk_access=1, tanpa welcome email; roles awal={frappe.get_roles(USER_EMAIL)}",
		)
	except Exception as e:
		check("fixture_user", False, f"{type(e).__name__}: {e}")
		raise GateAborted()

	frappe.set_user(USER_EMAIL)
	try:
		# Tanpa filter: kalau diberi filter Warehouse, user tanpa role ditolak
		# lebih dulu di validate_filters_permissions (ValidationError), bukan di
		# perm report. Yang diverifikasi di sini = penolakan akses report itu sendiri.
		frappe.desk.query_report.run(REPORT_NAME)
		check("report_denied_without_role", False, "query_report.run TIDAK ditolak untuk user tanpa role")
	except frappe.PermissionError as e:
		check("report_denied_without_role", True, f"PermissionError: {str(e)[:180]}")
	except Exception as e:
		check("report_denied_without_role", False, f"{type(e).__name__}: {str(e)[:180]}")
	finally:
		frappe.set_user("Administrator")

	try:
		user = frappe.get_doc("User", USER_EMAIL)
		user.add_roles("Gudang Barang Jadi", "Stock User")  # varargs
		frappe.clear_cache(user=USER_EMAIL)

		# --- Perm ref_doctype (keputusan W3: ref_doctype = "Stock Entry") ---
		# Keputusan orchestrator 2026-09-20: Custom DocPerm Material Request
		# (pemilik production_app, R7) men-set report=0 utk semua role gudang
		# sehingga gerbang native query_report.run
		# (frappe/desk/query_report.py:40-45) selalu menolak; ref_doctype report
		# dipindah ke "Stock Entry" yang ber-report=1 — tanpa menyentuh DocPerm.
		from frappe.permissions import get_role_permissions

		se_perm_fixture = get_role_permissions(frappe.get_meta("Stock Entry"), user=USER_EMAIL)
		mr_perm_fixture = get_role_permissions(frappe.get_meta("Material Request"), user=USER_EMAIL)
		check(
			"ref_doctype_report_perm",
			bool(se_perm_fixture.get("report")),
			f"fixture user report@SE={bool(se_perm_fixture.get('report'))}, "
			f"report@MR={bool(mr_perm_fixture.get('report'))} (roles={frappe.get_roles(USER_EMAIL)})",
		)

		frappe.set_user(USER_EMAIL)
		try:
			res = frappe.desk.query_report.run(REPORT_NAME, filters={"gudang_tujuan": target})
			blob = json.dumps(res.get("result", []), default=str)
			found = sum(1 for name in mr_names.values() if name in blob)
			check(
				"report_allowed_with_roles",
				found == 3,
				f"lulus sebagai {USER_EMAIL} (roles={frappe.get_roles(USER_EMAIL)}); {found}/3 baris MR fixture ada di hasil",
			)
		except Exception as e:
			check(
				"report_allowed_with_roles",
				False,
				f"{type(e).__name__}: {str(e)[:220]} (roles={frappe.get_roles(USER_EMAIL)})",
			)
		finally:
			frappe.set_user("Administrator")
	except Exception as e:
		frappe.set_user("Administrator")
		check("report_allowed_with_roles", False, f"pemberian role gagal: {type(e).__name__}: {e}")


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
	"""Bersihkan semua residu ber-prefix ZZTEST-W3. Idempoten (pre-clean & teardown)."""
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

	# Urutan: SE -> MR -> Serial and Batch Bundle -> Batch -> Bin -> Item -> User + log
	for name in frappe.get_all("Stock Entry", filters={"name": ("like", PREFIX + "%")}, pluck="name"):
		safe(f"SE {name}", lambda n=name: cancel_delete("Stock Entry", n))
	for name in frappe.get_all("Material Request", filters={"name": ("like", PREFIX + "%")}, pluck="name"):
		safe(f"MR {name}", lambda n=name: cancel_delete("Material Request", n))
	for name in frappe.get_all(
		"Serial and Batch Bundle", filters={"item_code": ("like", PREFIX + "%")}, pluck="name"
	):
		safe(f"SABB {name}", lambda n=name: cancel_delete("Serial and Batch Bundle", n))
	for name in frappe.get_all("Batch", filters={"name": ("like", PREFIX + "%")}, pluck="name"):
		safe(f"Batch {name}", lambda n=name: frappe.delete_doc("Batch", n, force=1, ignore_missing=True))
	safe("SLE", lambda: frappe.db.delete("Stock Ledger Entry", {"item_code": ("like", PREFIX + "%")}))
	safe("Repost", lambda: frappe.db.delete("Repost Item Valuation", {"item_code": ("like", PREFIX + "%")}))
	safe("Bin", lambda: frappe.db.delete("Bin", {"item_code": ("like", PREFIX + "%")}))
	# Item: situs memakai naming series, jadi cocokkan name ATAU item_code;
	# tambah item_name (dash & spasi) — rename bisa gagal dan meninggalkan
	# item bernama auto dengan item_name ber-prefix (temuan W6: ITEM00248).
	for name in frappe.get_all(
		"Item",
		or_filters=[
			["Item", "name", "like", PREFIX + "%"],
			["Item", "item_code", "like", PREFIX + "%"],
			["Item", "item_name", "like", PREFIX + "%"],
			["Item", "item_name", "like", PREFIX.replace("-", " ") + "%"],
		],
		pluck="name",
	):
		safe(f"Item {name}", lambda n=name: frappe.delete_doc("Item", n, force=1, ignore_missing=True))
	for name in frappe.get_all("User", filters={"name": ("like", PREFIX + "%")}, pluck="name"):
		safe(f"User {name}", lambda n=name: frappe.delete_doc("User", n, force=1, ignore_missing=True))
	safe("Sessions", lambda: frappe.db.delete("Sessions", {"user": ("like", PREFIX + "%")}))
	safe("ActivityLog.user", lambda: frappe.db.delete("Activity Log", {"user": ("like", PREFIX + "%")}))
	if frappe.db.has_column("Activity Log", "for_user"):
		safe(
			"ActivityLog.for_user",
			lambda: frappe.db.delete("Activity Log", {"for_user": ("like", PREFIX + "%")}),
		)
	# kolom Version di v16: ref_doctype + docname (bukan document_name)
	safe("Version", lambda: frappe.db.delete("Version", {"docname": ("like", PREFIX + "%")}))

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
