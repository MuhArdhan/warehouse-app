// Keep Pick List quantities aligned with the warehouse UOM used by other stock transactions.
frappe.ui.form.on("Pick List Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
		// Native ERPNext fills Stock UOM first. Apply the warehouse UOM after
		// that request completes, using the same permissioned endpoint as other forms.
		frappe.after_ajax(() => {
			frappe.db.get_value("Item", row.item_code, ["custom_default_uom_warehouse", "stock_uom"]).then((r) => {
				const item = r.message || {};
				const uom = item.custom_default_uom_warehouse || item.stock_uom;
				if (uom) frappe.model.set_value(cdt, cdn, "uom", uom);
			});
		});
	},
	batch_no(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.batch_no || !row.item_code || row.warehouse) return;
		frappe.call({
			method: "warehouse_app.overrides.pick_list.get_batch_warehouse",
			args: { batch_no: row.batch_no, item_code: row.item_code },
			callback(r) {
				if (r.message && r.message.warehouse) {
					frappe.model.set_value(cdt, cdn, "warehouse", r.message.warehouse);
				}
			},
		});
	},
	qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code || !row.conversion_factor) return;
		frappe.model.set_value(cdt, cdn, "stock_qty", flt(row.qty) * flt(row.conversion_factor));
	},
	conversion_factor(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
		frappe.model.set_value(cdt, cdn, "stock_qty", flt(row.qty) * (flt(row.conversion_factor) || 1));
	},
});
