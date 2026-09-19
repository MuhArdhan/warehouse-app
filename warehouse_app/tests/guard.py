# Copyright (c) 2026, Muhammad Yusuf Tri Daryanto
# License: MIT

# Guard residu fixture + perm native untuk warehouse_app.
# Dipakai gate W3 dan dipakai ulang W6 (IMPLEMENTATION_PLAN.md §5 Fase E).
#
# Jalankan:
#   docker exec erpnext-new-backend-1 bench --site frontend execute \
#       warehouse_app.tests.guard.run_guard
#
# ok hanya bila: semua count residu ber-prefix "ZZTEST-W" = 0, Custom DocPerm
# parent "Company" IDENTIK dengan baseline tercatat (bukan nol absolut — lihat
# komentar COMPANY_CDP_BASELINE), dan DocPerm standar Company role "Stock User"
# read == 1. Output: TEPAT satu baris GATE_JSON:{...} (ok, checks).

import json

import frappe
from frappe.utils import cint

PREFIX = "ZZTEST-W"

# Invariant Custom DocPerm Company: BUKAN nol absolut. Situs frontend punya 12
# baris pre-existing — 9× dibuat 2022-01-25, 2× Feb-2026 (owner Administrator),
# 1× "ALL ROLE" 2026-09-08 (owner ropierpnext@gmail.com); nol di antaranya
# dibuat warehouse_app, dan warehouse_app tidak boleh menyentuh DocPerm milik
# pihak lain (R7). Baris "Stock User" read=1 di sini justru yang menjaga akses
# read Company user gudang (Custom DocPerm menggantikan DocPerm standar —
# frappe/model/meta.py:640-653). Guard membandingkan snapshot
# (role, read, write, create, submit) terhadap baseline tercatat di bawah:
# ok hanya bila identik — baris baru/dihapus/berubah (termasuk penambahan
# role gudang apa pun) membuat guard gagal. Perubahan bisnis yang memang
# disengaja wajib disertai update baseline ini secara sadar.
# Snapshot diambil 2026-09-20 (frappe.get_all Custom DocPerm parent=Company).
COMPANY_CDP_BASELINE = (
	("ALL ROLE", 1, 0, 0, 0),
	("Accounts Manager", 1, 1, 1, 0),
	("Accounts User", 1, 0, 0, 0),
	("Auditor", 0, 0, 0, 0),
	("Employee", 1, 0, 0, 0),
	("Employee Self Service", 1, 0, 0, 0),
	("HR Manager", 1, 1, 1, 0),
	("Projects User", 1, 0, 0, 0),
	("Purchase User", 1, 0, 0, 0),
	("Sales User", 1, 0, 0, 0),
	("Stock User", 1, 0, 0, 0),
	("System Manager", 1, 1, 1, 0),
)


def count_residue(prefix=PREFIX):
	like = prefix + "%"
	counts = {
		# Item dihitung dari name ATAU item_code (situs bisa memakai naming series,
		# sehingga name saja belum tentu ber-prefix).
		"Item": frappe.db.count("Item", {"name": ("like", like)})
		+ frappe.db.count(
			"Item",
			{"item_code": ("like", like), "name": ("not like", like)},
		),
		"Material Request": frappe.db.count("Material Request", {"name": ("like", like)}),
		"Stock Entry": frappe.db.count("Stock Entry", {"name": ("like", like)}),
		"User": frappe.db.count("User", {"name": ("like", like)}),
		"Batch": frappe.db.count("Batch", {"name": ("like", like)}),
		"Serial and Batch Bundle": frappe.db.count(
			"Serial and Batch Bundle", {"item_code": ("like", like)}
		),
		"Bin": frappe.db.count("Bin", {"item_code": ("like", like)}),
		"Session": frappe.db.count("Sessions", {"user": ("like", like)}),
	}
	counts["Activity Log"] = frappe.db.count("Activity Log", {"user": ("like", like)})
	# Kolom `for_user` tidak ada di semua versi (v16 di situs ini: tidak ada).
	if frappe.db.has_column("Activity Log", "for_user"):
		counts["Activity Log"] += frappe.db.count("Activity Log", {"for_user": ("like", like)})
	return counts


def run_guard():
	residue = count_residue()

	company_cdps = frappe.get_all(
		"Custom DocPerm",
		filters={"parent": "Company"},
		fields=["role", "read", "write", "create", "submit"],
		limit_page_length=0,
	)
	current = tuple(
		sorted(
			(d["role"], cint(d["read"]), cint(d["write"]), cint(d["create"]), cint(d["submit"]))
			for d in company_cdps
		)
	)
	baseline = tuple(sorted(COMPANY_CDP_BASELINE))
	cdp_ok = current == baseline
	if cdp_ok:
		cdp_evidence = (
			f"{len(current)} baris identik baseline tercatat "
			"(12 baris pre-existing, nol dari warehouse_app)"
		)
	else:
		added = sorted(set(current) - set(baseline))
		removed = sorted(set(baseline) - set(current))
		cdp_evidence = (
			f"GAGAL: {len(current)} baris != baseline {len(baseline)}; "
			f"added={added}; removed={removed}"
		)

	stock_user_company_read = cint(
		frappe.db.get_value("DocPerm", {"parent": "Company", "role": "Stock User"}, "read")
	)

	checks = {f"residue[{k}]": f"{v} (target 0)" for k, v in residue.items()}
	checks["custom_docperm_company"] = cdp_evidence
	checks["stock_user_company_read"] = f"{stock_user_company_read} (target 1)"

	ok = (
		all(v == 0 for v in residue.values())
		and cdp_ok
		and stock_user_company_read == 1
	)
	payload = {"ok": ok, "checks": checks}
	print("GATE_JSON:" + json.dumps(payload, ensure_ascii=False))
	return payload
