import frappe
from frappe import _, bold
from frappe.utils import flt

from erpnext.stock.doctype.pick_list.pick_list import PickList

from warehouse_app.overrides.batch_uom import get_item_uom_conversion_factor


@frappe.whitelist()
def get_batch_warehouse(batch_no, item_code=None):
	"""Return a stock warehouse containing the selected batch."""
	from warehouse_app.overrides.batch_uom import _orig_get_batch_qty

	locations = _orig_get_batch_qty(batch_no=batch_no, item_code=item_code)
	if isinstance(locations, list):
		for location in locations:
			if location.get("warehouse") and flt(location.get("qty")) > 0:
				return {"warehouse": location.get("warehouse")}
	return {"warehouse": None}


def apply_pick_list_uom_conversion(doc):
	"""Use the warehouse UOM while keeping Pick List stock quantities in stock UOM."""
	for row in doc.get("locations") or []:
		item_code = row.get("item_code")
		if not item_code:
			continue

		stock_uom = row.get("stock_uom") or frappe.db.get_value("Item", item_code, "stock_uom")
		warehouse_uom = frappe.db.get_value("Item", item_code, "custom_default_uom_warehouse") or stock_uom
		if not stock_uom or not warehouse_uom:
			continue

		result = get_item_uom_conversion_factor(item_code, warehouse_uom)
		conversion_factor = flt(result.get("conversion_factor")) or 1.0
		previous_uom = row.get("uom")
		row.stock_uom = stock_uom
		row.uom = warehouse_uom
		row.conversion_factor = conversion_factor

		# Rows generated from a source document already have stock_qty. Convert
		# that quantity for display; manually entered rows use qty in warehouse UOM.
		if flt(row.get("stock_qty")) and previous_uom in (None, "", stock_uom):
			row.qty = flt(row.stock_qty) / conversion_factor
		else:
			row.stock_qty = flt(row.get("qty")) * conversion_factor


class WarehousePickList(PickList):
	def _fill_batch_warehouses(self):
		"""Fill the read-only child warehouse when a batch was selected manually."""
		from warehouse_app.overrides.batch_uom import _orig_get_batch_qty

		for row in self.get("locations") or []:
			if row.get("warehouse") or not row.get("batch_no") or not row.get("item_code"):
				continue
			locations = _orig_get_batch_qty(batch_no=row.batch_no, item_code=row.item_code)
			if isinstance(locations, list):
				for location in locations:
					if location.get("batch_no") == row.batch_no and location.get("warehouse"):
						row.warehouse = location.get("warehouse")
						break

	def validate_stock_qty(self):
		"""Validate picked quantities in Stock UOM, including auto-pick batch lists."""
		from warehouse_app.overrides.batch_uom import _orig_get_batch_qty

		for row in self.get("locations") or []:
			if not row.picked_qty:
				continue

			if row.batch_no:
				batch_qty = _orig_get_batch_qty(
					batch_no=row.batch_no,
					warehouse=row.warehouse,
					item_code=row.item_code,
				)
				if isinstance(batch_qty, list):
					batch_qty = sum(
						flt(entry.get("qty"))
						for entry in batch_qty
						if not entry.get("batch_no") or entry.get("batch_no") == row.batch_no
					)
				elif isinstance(batch_qty, dict):
					batch_qty = batch_qty.get(row.batch_no, 0)
				batch_qty = flt(batch_qty)

				if flt(row.picked_qty) > batch_qty:
					frappe.throw(
						_("At Row #{0}: The picked quantity {1} for the item {2} is greater than available stock {3} for the batch {4} in the warehouse {5}. Please restock the item.").format(
							row.idx, row.picked_qty, row.item_code, batch_qty, row.batch_no, bold(row.warehouse)
						),
						title=_("Insufficient Stock"),
					)
				continue

			bin_qty = flt(frappe.db.get_value("Bin", {"item_code": row.item_code, "warehouse": row.warehouse}, "actual_qty"))
			if flt(row.picked_qty) > bin_qty:
				frappe.throw(
					_("At Row #{0}: The picked quantity {1} for the item {2} is greater than available stock {3} in the warehouse {4}.").format(
						row.idx, row.picked_qty, bold(row.item_code), bin_qty, bold(row.warehouse)
					),
					title=_("Insufficient Stock"),
				)

	def validate(self):
		self._fill_batch_warehouses()
		# Native Pick List normally fills locations in before_save, but its
		# validation reads row.warehouse earlier. Populate them first so batch
		# quantity validation receives a scalar quantity instead of a batch list.
		if not self.pick_manually:
			self.set_item_locations()
		apply_pick_list_uom_conversion(self)
		super().validate()

	def before_save(self):
		super().before_save()
		# Native before_save may regenerate locations for automatic picking.
		apply_pick_list_uom_conversion(self)
