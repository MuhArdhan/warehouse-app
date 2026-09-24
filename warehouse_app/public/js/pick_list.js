// Picked Qty is entered in warehouse UOM; native picked_qty stays in Stock UOM.
const PICKED_QTY_UOM_FIELD = "custom_picked_qty_warehouse_uom";

function get_pick_list_factor(row) {
	if (!row || !row.item_code || !row.uom || !row.stock_uom || row.uom === row.stock_uom) return 1;
	return flt(row.conversion_factor) || 1;
}

function configure_picked_qty_grid(frm) {
	const grid = frm.fields_dict.locations && frm.fields_dict.locations.grid;
	if (!grid) return;
	grid.update_docfield_property("picked_qty", "hidden", 1);
	grid.update_docfield_property(PICKED_QTY_UOM_FIELD, "label", __("Picked Qty (Warehouse UOM)"));
	grid.refresh();
}

function sync_picked_qty_to_stock_uom(row) {
	if (!row || row[PICKED_QTY_UOM_FIELD] === undefined || row[PICKED_QTY_UOM_FIELD] === null) return;
	row.picked_qty = flt(row[PICKED_QTY_UOM_FIELD]) * get_pick_list_factor(row);
}

function populate_picked_qty_uom(frm) {
	let changed = false;
	(frm.doc.locations || []).forEach((row) => {
		if (row[PICKED_QTY_UOM_FIELD] === undefined || row[PICKED_QTY_UOM_FIELD] === null) {
			row[PICKED_QTY_UOM_FIELD] = flt(row.picked_qty) / get_pick_list_factor(row);
			changed = true;
		}
	});
	if (changed) frm.refresh_field("locations");
}

frappe.ui.form.on("Pick List", {
	setup(frm) {
		configure_picked_qty_grid(frm);
	},
	refresh(frm) {
		configure_picked_qty_grid(frm);
		populate_picked_qty_uom(frm);
	},
	before_save(frm) {
		(frm.doc.locations || []).forEach(sync_picked_qty_to_stock_uom);
	},
	before_submit(frm) {
		(frm.doc.locations || []).forEach(sync_picked_qty_to_stock_uom);
	},
	after_save(frm) {
		configure_picked_qty_grid(frm);
		populate_picked_qty_uom(frm);
	},
	after_submit(frm) {
		configure_picked_qty_grid(frm);
		populate_picked_qty_uom(frm);
	},
});

frappe.ui.form.on("Pick List Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
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
		if (!row.item_code) return;
		frappe.model.set_value(cdt, cdn, "stock_qty", flt(row.qty) * get_pick_list_factor(row));
	},
	conversion_factor(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
		frappe.model.set_value(cdt, cdn, "stock_qty", flt(row.qty) * get_pick_list_factor(row));
		sync_picked_qty_to_stock_uom(row);
	},
	custom_picked_qty_warehouse_uom(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		sync_picked_qty_to_stock_uom(row);
	},
});
