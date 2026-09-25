"""Sales Order additions owned by warehouse_app."""

from collections import defaultdict

import frappe
from frappe import _


@frappe.whitelist()
def create_pick_lists(source_name: str) -> dict:
	"""Split a Sales Order Pick List into native wet/dry drafts when required."""

	from erpnext.selling.doctype.sales_order.sales_order import create_pick_list

	# Keep ERPNext's permission checks, quantity calculation, reservation guard,
	# product-bundle expansion, and location selection from the native mapper.
	mapped_pick_list = create_pick_list(source_name)
	sales_order = frappe.get_doc("Sales Order", source_name)

	item_codes = {row.item_code for row in sales_order.items if row.item_code}
	wet_item_codes = set(
		frappe.get_all(
			"Item",
			filters={"name": ["in", item_codes], "custom_wet_item": 1},
			pluck="name",
		)
	)
	source_item_by_row = {row.name: row.item_code for row in sales_order.items}
	locations_by_category = defaultdict(list)

	for location in mapped_pick_list.locations:
		item_code = source_item_by_row.get(location.sales_order_item)
		if not item_code:
			frappe.throw(
				_("Pick List row for item {0} is missing its Sales Order Item reference.").format(
					frappe.bold(location.item_code)
				)
			)

		category = "Wet" if item_code in wet_item_codes else "Dry"
		locations_by_category[category].append(location)

	groups = [(category, locations_by_category[category]) for category in ("Wet", "Dry") if locations_by_category[category]]
	if not groups:
		frappe.throw(_("No Pick List item locations could be created. Restock the items and try again."))

	if len(groups) == 1:
		# Match ERPNext's normal flow: open one unsaved Pick List form.
		mapped_pick_list.set("locations", [])
		for location in groups[0][1]:
			mapped_pick_list.append("locations", frappe.copy_doc(location).as_dict())
		return {"pick_list": mapped_pick_list.as_dict()}

	created_pick_lists = []
	for category, locations in groups:
		pick_list = frappe.copy_doc(mapped_pick_list)
		# Preserve ERPNext's default: Pick Manually remains unchecked.
		pick_list.set("locations", [])
		for location in locations:
			pick_list.append("locations", frappe.copy_doc(location).as_dict())

		pick_list.insert()
		created_pick_lists.append({"name": pick_list.name, "category": category})

	return {"draft_pick_lists": created_pick_lists}
