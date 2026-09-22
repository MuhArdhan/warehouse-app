import frappe
from erpnext.stock.doctype.batch.batch import Batch
from frappe.utils import flt


class WarehouseBatch(Batch):
	"""
	Override of ERPNext's Batch DocType for warehouse_app.
	Ensures Batch UOM (stock_uom field) follows custom_default_uom_warehouse
	from Item Master if present, falling back to Item's standard stock_uom.
	Also ensures batch_qty and custom_qty_in_uom reflect quantity in warehouse UOM (Pack).
	"""

	def validate(self):
		self.set_batch_uom()
		self.set_warehouse_qty()
		super().validate()

	def before_insert(self):
		if hasattr(super(), "before_insert"):
			super().before_insert()
		self.set_batch_uom()
		self.set_warehouse_qty()

	def onload(self):
		super().onload()
		if self.item:
			self.set_batch_uom()
			self.set_warehouse_qty()

	def recalculate_batch_qty(self):
		super().recalculate_batch_qty()
		if hasattr(self, "custom_qty_in_uom"):
			self.db_set("custom_qty_in_uom", self.batch_qty)
			self.custom_qty_in_uom = self.batch_qty

	def get_conversion_factor(self):
		if not self.item or not self.stock_uom:
			return 1.0

		item_stock_uom = frappe.db.get_value("Item", self.item, "stock_uom")
		if self.stock_uom and item_stock_uom and self.stock_uom != item_stock_uom:
			cf = frappe.db.get_value(
				"UOM Conversion Detail",
				{"parent": self.item, "parenttype": "Item", "uom": self.stock_uom},
				"conversion_factor",
			)
			if cf:
				return flt(cf)
		return 1.0

	def set_batch_uom(self):
		if not self.item:
			return

		item_info = frappe.db.get_value(
			"Item",
			self.item,
			["custom_default_uom_warehouse", "stock_uom"],
			as_dict=True,
		)
		if not item_info:
			return

		custom_uom = item_info.get("custom_default_uom_warehouse")
		if custom_uom:
			self.stock_uom = custom_uom
			if hasattr(self, "custom_default_uom_warehouse"):
				self.custom_default_uom_warehouse = custom_uom
		elif not self.stock_uom:
			self.stock_uom = item_info.get("stock_uom")

	def set_warehouse_qty(self):
		if not self.item:
			return

		cf = self.get_conversion_factor()
		if hasattr(self, "custom_uom_conversion_factor"):
			self.custom_uom_conversion_factor = cf
		if hasattr(self, "custom_qty_in_uom"):
			self.custom_qty_in_uom = self.batch_qty
