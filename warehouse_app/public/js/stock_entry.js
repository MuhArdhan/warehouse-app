// Client-side script for Stock Entry in warehouse_app
// Ensures custom_default_uom_warehouse and conversion rate are applied in Stock Entry Detail

frappe.ui.form.on("Stock Entry Detail", {
	item_code: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.item_code) return;

		frappe.db.get_value(
			"Item",
			row.item_code,
			["custom_default_uom_warehouse", "stock_uom"],
			function (r) {
				if (r && r.custom_default_uom_warehouse && r.custom_default_uom_warehouse !== r.stock_uom) {
					frappe.model.set_value(cdt, cdn, "uom", r.custom_default_uom_warehouse);
				}
			}
		);
	},
	uom: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.item_code && row.uom) {
			if (row.uom === row.stock_uom) {
				frappe.model.set_value(cdt, cdn, "conversion_factor", 1.0);
				frappe.model.set_value(cdt, cdn, "transfer_qty", flt(row.qty));
				return;
			}
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "UOM Conversion Detail",
					filters: {
						parent: row.item_code,
						parenttype: "Item",
						uom: row.uom,
					},
					fieldname: "conversion_factor",
				},
				callback: function (r) {
					if (r.message && r.message.conversion_factor) {
						let cf = flt(r.message.conversion_factor);
						frappe.model.set_value(cdt, cdn, "conversion_factor", cf);
						frappe.model.set_value(cdt, cdn, "transfer_qty", flt(row.qty) * cf);
					}
				},
			});
		}
	},
	qty: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let cf = flt(row.conversion_factor) || 1.0;
		let expected_transfer = flt(row.qty) * cf;
		if (flt(row.transfer_qty) !== expected_transfer) {
			frappe.model.set_value(cdt, cdn, "transfer_qty", expected_transfer);
		}
	},
	batch_no: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.batch_no) return;

		frappe.db.get_value(
			"Batch",
			row.batch_no,
			["stock_uom"],
			function (b) {
				if (b && b.stock_uom && b.stock_uom !== row.uom) {
					frappe.model.set_value(cdt, cdn, "uom", b.stock_uom);
				}
			}
		);
	},
});
