// Client-side script for Purchase Invoice in warehouse_app
// Ensures custom_default_uom_warehouse and conversion rate are applied in Purchase Invoice Item

frappe.ui.form.on("Purchase Invoice Item", {
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
				frappe.model.set_value(cdt, cdn, "stock_qty", flt(row.qty));
				return;
			}
			frappe.call({
				method: "warehouse_app.overrides.batch_uom.get_item_uom_conversion_factor",
				args: { item_code: row.item_code, uom: row.uom },
				callback: function (r) {
					if (r.message && r.message.conversion_factor) {
						let cf = flt(r.message.conversion_factor);
						frappe.model.set_value(cdt, cdn, "conversion_factor", cf);
						frappe.model.set_value(cdt, cdn, "stock_qty", flt(row.qty) * cf);
					}
				},
			});
		}
	},
	qty: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let cf = flt(row.conversion_factor) || 1.0;
		let expected_stock_qty = flt(row.qty) * cf;
		if (flt(row.stock_qty) !== expected_stock_qty) {
			frappe.model.set_value(cdt, cdn, "stock_qty", expected_stock_qty);
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
