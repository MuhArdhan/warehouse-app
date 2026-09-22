import frappe
from frappe.utils import flt
import erpnext.stock.serial_batch_bundle as sbb


def get_batch_conversion_factor(batch_no, item_code=None):
	if not batch_no and not item_code:
		return 1.0

	item = item_code or (frappe.db.get_value("Batch", batch_no, "item") if batch_no else None)
	if not item:
		return 1.0

	batch_uom = frappe.db.get_value("Batch", batch_no, "stock_uom") if batch_no else None
	if not batch_uom:
		batch_uom = frappe.db.get_value("Item", item, "custom_default_uom_warehouse")

	item_stock_uom = frappe.db.get_value("Item", item, "stock_uom")

	if batch_uom and item_stock_uom and batch_uom != item_stock_uom:
		cf = frappe.db.get_value(
			"UOM Conversion Detail",
			{"parent": item, "parenttype": "Item", "uom": batch_uom},
			"conversion_factor",
		)
		if cf:
			return flt(cf)
	return 1.0


def get_batch_display_uom(batch_no, item_code=None):
	if not batch_no and not item_code:
		return None

	item = item_code or (frappe.db.get_value("Batch", batch_no, "item") if batch_no else None)
	batch_uom = frappe.db.get_value("Batch", batch_no, "stock_uom") if batch_no else None
	if not batch_uom and item:
		batch_uom = (
			frappe.db.get_value("Item", item, "custom_default_uom_warehouse")
			or frappe.db.get_value("Item", item, "stock_uom")
		)
	return batch_uom


def warehouse_update_batch_qty(voucher_type, voucher_no, docstatus, via_landed_cost_voucher=False):
	batches = sbb.get_batchwise_qty(voucher_type, voucher_no)
	if not batches:
		return

	precision = frappe.get_precision("Batch", "batch_qty")
	for batch, qty in batches.items():
		conversion_factor = get_batch_conversion_factor(batch)
		qty_in_warehouse_uom = flt(qty) / conversion_factor

		current_qty = sbb.get_batch_current_qty(batch)
		current_qty += flt(qty_in_warehouse_uom, precision) * (-1 if docstatus == 2 else 1)

		if not via_landed_cost_voucher and current_qty < 0:
			sbb.throw_negative_batch_validation(batch, current_qty)

		frappe.db.set_value("Batch", batch, "batch_qty", current_qty)
		if frappe.db.has_column("Batch", "custom_qty_in_uom"):
			frappe.db.set_value("Batch", batch, "custom_qty_in_uom", current_qty)


import erpnext.stock.serial_batch_bundle as sbb
import erpnext.stock.doctype.batch.batch as erpnext_batch
import erpnext.stock.doctype.stock_entry.stock_entry_utils as stock_entry_utils
import erpnext.controllers.queries as queries_module
import erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle as sbb_bundle

_orig_get_batch_qty = erpnext_batch.get_batch_qty
_orig_split_batch = erpnext_batch.split_batch
_orig_make_stock_entry = stock_entry_utils.make_stock_entry
_orig_get_batch_no = queries_module.get_batch_no
_orig_add_serial_batch_ledgers = sbb_bundle.add_serial_batch_ledgers
_orig_get_serial_batch_ledgers = sbb_bundle.get_serial_batch_ledgers
_orig_get_auto_data = sbb_bundle.get_auto_data


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def warehouse_get_batch_no(doctype, txt, searchfield, start, page_len, filters):
	batches = _orig_get_batch_no(doctype, txt, searchfield, start, page_len, filters)
	if not batches:
		return batches

	item_code = None
	if isinstance(filters, dict):
		item_code = filters.get("item_code") or filters.get("item")
	elif isinstance(filters, list):
		for f in filters:
			if isinstance(f, (list, tuple)) and len(f) >= 4 and f[1] in ("item_code", "item"):
				item_code = f[3]
				break

	res = []
	for row in batches:
		row_list = list(row)
		if len(row_list) > 1 and row_list[1] is not None:
			batch_no = row_list[0]
			cf = get_batch_conversion_factor(batch_no, item_code)
			display_uom = get_batch_display_uom(batch_no, item_code)
			raw_qty = flt(row_list[1])
			if cf and cf > 1.0:
				qty_in_uom = raw_qty / cf
			else:
				qty_in_uom = raw_qty

			qty_str = f"{flt(qty_in_uom, 4):g}"
			if display_uom:
				row_list[1] = f"{qty_str} {display_uom}"
			else:
				row_list[1] = qty_str

		res.append(tuple(row_list) if isinstance(row, tuple) else row_list)

	return res


@frappe.whitelist()
def warehouse_get_batch_qty(
	batch_no=None,
	warehouse=None,
	item_code=None,
	creation=None,
	posting_datetime=None,
	posting_date=None,
	posting_time=None,
	ignore_voucher_nos=None,
	for_stock_levels=False,
	consider_negative_batches=False,
	do_not_check_future_batches=False,
	ignore_reserved_stock=False,
):
	batches = _orig_get_batch_qty(
		batch_no=batch_no,
		warehouse=warehouse,
		item_code=item_code,
		creation=creation,
		posting_datetime=posting_datetime,
		posting_date=posting_date,
		posting_time=posting_time,
		ignore_voucher_nos=ignore_voucher_nos,
		for_stock_levels=for_stock_levels,
		consider_negative_batches=consider_negative_batches,
		do_not_check_future_batches=do_not_check_future_batches,
		ignore_reserved_stock=ignore_reserved_stock,
	)

	if isinstance(batches, (int, float)):
		cf = get_batch_conversion_factor(batch_no, item_code)
		if cf and cf > 1.0:
			batches = flt(batches) / cf
	elif isinstance(batches, list):
		for row in batches:
			b_no = row.get("batch_no") or batch_no
			if b_no and "qty" in row:
				cf = get_batch_conversion_factor(b_no, item_code)
				if cf and cf > 1.0:
					row["qty"] = flt(row["qty"]) / cf

	return batches


@frappe.whitelist()
def warehouse_add_serial_batch_ledgers(
	entries: list | str,
	child_row: dict | str,
	doc: dict | str,
	warehouse: str | None = None,
	do_not_save: bool = False,
):
	parsed_child_row = sbb_bundle.parse_json(child_row) if isinstance(child_row, str) else child_row
	parsed_entries = sbb_bundle.parse_json(entries) if isinstance(entries, str) else entries

	if parsed_child_row and parsed_entries and isinstance(parsed_entries, list):
		item_code = parsed_child_row.get("item_code") or parsed_child_row.get("rm_item_code")
		stock_uom = parsed_child_row.get("stock_uom") or (frappe.db.get_value("Item", item_code, "stock_uom") if item_code else None)
		uom = parsed_child_row.get("uom")

		if uom and stock_uom and uom == stock_uom:
			cf = 1.0
		else:
			cf = flt(parsed_child_row.get("conversion_factor")) or 1.0
			if not cf or cf <= 1.0:
				batch_no = parsed_entries[0].get("batch_no") if parsed_entries else None
				cf = get_batch_conversion_factor(batch_no, item_code)

		if cf and cf > 1.0:
			converted_entries = []
			for row in parsed_entries:
				row_copy = dict(row)
				if "qty" in row_copy and row_copy["qty"] is not None:
					row_copy["qty"] = flt(row_copy["qty"]) * cf
				converted_entries.append(row_copy)
			entries = converted_entries

	return _orig_add_serial_batch_ledgers(entries, child_row, doc, warehouse=warehouse, do_not_save=do_not_save)


@frappe.whitelist()
def warehouse_get_serial_batch_ledgers(
	item_code=None, docstatus=None, voucher_no=None, name=None, child_row=None
):
	ledgers = _orig_get_serial_batch_ledgers(
		item_code=item_code,
		docstatus=docstatus,
		voucher_no=voucher_no,
		name=name,
		child_row=child_row,
	)
	if not ledgers:
		return ledgers

	parsed_child_row = sbb_bundle.parse_json(child_row) if isinstance(child_row, str) else child_row
	child_uom = parsed_child_row.get("uom") if parsed_child_row else None
	child_cf = flt(parsed_child_row.get("conversion_factor")) if parsed_child_row else None

	for row in ledgers:
		i_code = row.get("item_code") or item_code
		b_no = row.get("batch_no")
		stock_uom = frappe.db.get_value("Item", i_code, "stock_uom") if i_code else None

		if child_uom and stock_uom and child_uom == stock_uom:
			continue

		cf = child_cf if (child_cf and child_cf > 1.0) else get_batch_conversion_factor(b_no, i_code)
		if cf and cf > 1.0 and "qty" in row and row["qty"] is not None:
			row["qty"] = flt(row["qty"]) / cf

	return ledgers


@frappe.whitelist()
def warehouse_get_auto_data(**kwargs):
	item_code = kwargs.get("item_code")
	has_batch_no = kwargs.get("has_batch_no")
	has_serial_no = kwargs.get("has_serial_no")

	cf = 1.0
	if has_batch_no and not has_serial_no and item_code:
		cf = get_batch_conversion_factor(None, item_code)

	orig_qty = flt(kwargs.get("qty")) if kwargs.get("qty") is not None else None
	if cf and cf > 1.0 and orig_qty:
		kwargs["qty"] = orig_qty * cf

	batches = _orig_get_auto_data(**kwargs)
	if not batches or not isinstance(batches, list):
		return batches

	if cf and cf > 1.0:
		for row in batches:
			b_no = row.get("batch_no")
			row_cf = get_batch_conversion_factor(b_no, item_code) if b_no else cf
			if row_cf and row_cf > 1.0 and "qty" in row and row["qty"] is not None:
				row["qty"] = flt(row["qty"]) / row_cf

	return batches



@frappe.whitelist()
def warehouse_make_stock_entry(**args):
	batch_no = args.get("batch_no")
	if batch_no:
		cf = get_batch_conversion_factor(batch_no)
		if cf and cf > 1.0:
			args = frappe._dict(args)
			orig_qty = flt(args.qty)
			stock_qty = orig_qty * cf

			from erpnext.stock.serial_batch_bundle import SerialBatchCreation
			from erpnext.stock.utils import get_combine_datetime
			from frappe.utils import today

			s = frappe.new_doc("Stock Entry")
			if args.posting_date or args.posting_time:
				s.set_posting_time = 1
			if args.posting_date:
				s.posting_date = args.posting_date
			if args.posting_time:
				s.posting_time = args.posting_time
			if args.inspection_required:
				s.inspection_required = args.inspection_required
			if not args.posting_date:
				s.posting_date = today()

			source = args.from_warehouse or args.source
			target = args.to_warehouse or args.target
			item_code = args.item_code or args.item

			if source and target:
				s.purpose = "Material Transfer"
			elif source:
				s.purpose = "Material Issue"
			else:
				s.purpose = "Material Receipt"
			if args.purpose:
				s.purpose = args.purpose

			if not args.company:
				if source:
					args.company = frappe.db.get_value("Warehouse", source, "company")
				elif target:
					args.company = frappe.db.get_value("Warehouse", target, "company")

			import erpnext
			s.company = args.company or erpnext.get_default_company()
			if not args.cost_center:
				args.cost_center = frappe.get_value("Company", s.company, "cost_center")

			posting_datetime = None
			if s.posting_date and s.posting_time:
				posting_datetime = get_combine_datetime(s.posting_date, s.posting_time)

			bundle_id = (
				SerialBatchCreation(
					{
						"item_code": item_code,
						"warehouse": source or target,
						"voucher_type": "Stock Entry",
						"total_qty": stock_qty * (-1 if source else 1),
						"batches": frappe._dict({batch_no: stock_qty}),
						"serial_nos": args.serial_no,
						"type_of_transaction": "Outward" if source else "Inward",
						"company": s.company,
						"posting_datetime": posting_datetime,
						"rate": args.rate or args.basic_rate,
						"do_not_submit": True,
					}
				)
				.make_serial_and_batch_bundle()
				.name
			)

			batch_uom = frappe.db.get_value("Batch", batch_no, "stock_uom")
			s.append(
				"items",
				{
					"item_code": item_code,
					"s_warehouse": source,
					"t_warehouse": target,
					"qty": orig_qty,
					"uom": batch_uom,
					"conversion_factor": cf,
					"transfer_qty": stock_qty,
					"serial_and_batch_bundle": bundle_id,
					"basic_rate": args.rate or args.basic_rate,
					"cost_center": args.cost_center,
					"expense_account": args.expense_account,
				},
			)
			s.set_stock_entry_type()
			if not args.do_not_save:
				s.insert()
				if not args.do_not_submit:
					s.submit()
				s.load_from_db()
			return s

	return _orig_make_stock_entry(**args)


@frappe.whitelist()
def warehouse_split_batch(batch_no: str, item_code: str, warehouse: str, qty: float, new_batch_id: str | None = None):
	cf = get_batch_conversion_factor(batch_no)
	if cf and cf > 1.0:
		batch = frappe.get_doc(doctype="Batch", item=item_code, batch_id=new_batch_id).insert()
		qty = flt(qty)
		stock_qty = qty * cf

		company = frappe.db.get_value("Warehouse", warehouse, "company")
		from erpnext.stock.doctype.batch.batch import make_batch_bundle

		from_bundle_id = make_batch_bundle(
			item_code=item_code,
			warehouse=warehouse,
			batches=frappe._dict({batch_no: stock_qty}),
			company=company,
			type_of_transaction="Outward",
			qty=stock_qty,
		)

		to_bundle_id = make_batch_bundle(
			item_code=item_code,
			warehouse=warehouse,
			batches=frappe._dict({batch.name: stock_qty}),
			company=company,
			type_of_transaction="Inward",
			qty=stock_qty,
		)

		batch_uom = frappe.db.get_value("Batch", batch_no, "stock_uom")
		stock_entry = frappe.get_doc(
			doctype="Stock Entry",
			purpose="Repack",
			company=company,
			items=[
				dict(
					item_code=item_code,
					qty=qty,
					uom=batch_uom,
					conversion_factor=cf,
					transfer_qty=stock_qty,
					s_warehouse=warehouse,
					serial_and_batch_bundle=from_bundle_id,
				),
				dict(
					item_code=item_code,
					qty=qty,
					uom=batch_uom,
					conversion_factor=cf,
					transfer_qty=stock_qty,
					t_warehouse=warehouse,
					serial_and_batch_bundle=to_bundle_id,
				),
			],
		)
		stock_entry.set_stock_entry_type()
		stock_entry.insert()
		stock_entry.submit()

		return batch.name

	return _orig_split_batch(batch_no, item_code, warehouse, qty, new_batch_id)


def apply_patches():
	if sbb.update_batch_qty != warehouse_update_batch_qty:
		sbb.update_batch_qty = warehouse_update_batch_qty
	if erpnext_batch.get_batch_qty != warehouse_get_batch_qty:
		erpnext_batch.get_batch_qty = warehouse_get_batch_qty
	if erpnext_batch.split_batch != warehouse_split_batch:
		erpnext_batch.split_batch = warehouse_split_batch
	if stock_entry_utils.make_stock_entry != warehouse_make_stock_entry:
		stock_entry_utils.make_stock_entry = warehouse_make_stock_entry
	if queries_module.get_batch_no != warehouse_get_batch_no:
		queries_module.get_batch_no = warehouse_get_batch_no
	if sbb_bundle.add_serial_batch_ledgers != warehouse_add_serial_batch_ledgers:
		sbb_bundle.add_serial_batch_ledgers = warehouse_add_serial_batch_ledgers
	if sbb_bundle.get_serial_batch_ledgers != warehouse_get_serial_batch_ledgers:
		sbb_bundle.get_serial_batch_ledgers = warehouse_get_serial_batch_ledgers
	if sbb_bundle.get_auto_data != warehouse_get_auto_data:
		sbb_bundle.get_auto_data = warehouse_get_auto_data


# Apply on module import
apply_patches()


def sync_batch_qty(batch_no):
	batches = warehouse_get_batch_qty(batch_no=batch_no)
	total_qty = 0.0
	if batches:
		for row in batches:
			total_qty += flt(row.get("qty", 0.0))

	warehouse_qty = total_qty

	frappe.db.set_value("Batch", batch_no, "batch_qty", warehouse_qty, update_modified=False)
	if frappe.db.has_column("Batch", "custom_qty_in_uom"):
		frappe.db.set_value("Batch", batch_no, "custom_qty_in_uom", warehouse_qty, update_modified=False)


def sync_batch_qty_after_transaction(doc, method=None):
	batches = set()
	if doc.get("items"):
		for item in doc.items:
			if item.get("batch_no"):
				batches.add(item.batch_no)
			if item.get("serial_and_batch_bundle"):
				from erpnext.stock.serial_batch_bundle import get_serial_batch_list_from_item
				_, batch_list = get_serial_batch_list_from_item(item)
				for b in batch_list:
					batches.add(b)

	for batch_no in batches:
		sync_batch_qty(batch_no)


def apply_batch_uom_conversion(doc, method=None):
	"""
	Enforce conversion factor and stock quantity across all stock transactions
	so that warehouse/batch UOMs (e.g. Pack) are properly converted to stock_uom (Pcs)
	in Stock Ledger (e.g. 100 Pack * 12 = 1200 Pcs).

	Applies to:
	- Stock Entry (transfer_qty)
	- Purchase Receipt (stock_qty)
	- Delivery Note (stock_qty)
	- Sales Invoice (stock_qty)
	- Purchase Invoice (stock_qty)
	- Subcontracting Receipt (stock_qty)
	- Material Request (stock_qty)
	"""
	apply_patches()

	tables_to_check = ["items"]
	if doc.doctype == "Subcontracting Receipt":
		tables_to_check.append("supplied_items")

	for table_name in tables_to_check:
		items = doc.get(table_name)
		if not items:
			continue

		for item in items:
			item_code = item.get("item_code") or item.get("rm_item_code")
			if not item_code:
				continue

			# Ensure stock_uom is set
			if not item.get("stock_uom"):
				item.stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")

			# If uom is missing, fallback to batch stock_uom, custom_default_uom_warehouse, or stock_uom
			if not item.get("uom"):
				if hasattr(item, "batch_no") and item.batch_no:
					batch_uom = frappe.db.get_value("Batch", item.batch_no, "stock_uom")
					if batch_uom:
						item.uom = batch_uom
				if not item.get("uom"):
					custom_uom = frappe.db.get_value("Item", item_code, "custom_default_uom_warehouse")
					item.uom = custom_uom or item.stock_uom

			# Resolve conversion factor from UOM Conversion Detail
			if item.uom == item.stock_uom:
				item.conversion_factor = 1.0
			else:
				cf = frappe.db.get_value(
					"UOM Conversion Detail",
					{"parent": item_code, "parenttype": "Item", "uom": item.uom},
					"conversion_factor",
				)
				if cf:
					item.conversion_factor = flt(cf)

			conversion_factor = flt(item.conversion_factor) or 1.0
			qty = flt(item.qty)

			# Apply to transfer_qty for Stock Entry, or stock_qty for other documents
			if doc.doctype == "Stock Entry":
				prec = item.precision("transfer_qty") if hasattr(item, "precision") else 4
				item.transfer_qty = flt(qty * conversion_factor, prec)
			else:
				if hasattr(item, "stock_qty"):
					prec = item.precision("stock_qty") if hasattr(item, "precision") else 4
					item.stock_qty = flt(qty * conversion_factor, prec)
