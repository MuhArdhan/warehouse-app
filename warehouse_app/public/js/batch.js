// Client-side override for Batch DocType in warehouse_app
// Sets Batch UOM (stock_uom) from custom_default_uom_warehouse if available on Item
// and calculates custom_qty_in_uom (quantity in warehouse UOM)
// and displays Stock Levels in Batch UOM (matching batch_qty, e.g. 100 Pack)

frappe.ui.form.off("Batch", "make_dashboard");

frappe.ui.form.on("Batch", {
	refresh: function (frm) {
		if (frm.is_new() && frm.doc.item) {
			set_batch_uom_from_item(frm);
		}
		update_warehouse_qty(frm);
	},
	item: function (frm) {
		set_batch_uom_from_item(frm);
		update_warehouse_qty(frm);
	},
	make_dashboard: function (frm) {
		const request_id = frm.batch_dashboard_request_id;

		if (!frm.is_new()) {
			let for_stock_levels = 0;
			if (!frm.doc.batch_qty && frm.doc.expiry_date) {
				for_stock_levels = 1;
			}

			frappe.call({
				method: "erpnext.stock.doctype.batch.batch.get_batch_qty",
				args: {
					batch_no: frm.doc.name,
					item_code: frm.doc.item,
					for_stock_levels: for_stock_levels,
					consider_negative_batches: 1,
					ignore_reserved_stock: 1,
				},
				callback: function (r) {
					if (request_id !== frm.batch_dashboard_request_id) {
						return;
					}

					if (!r.message || r.message.length === 0) {
						frm.dashboard.add_comment(__("No stock available for this batch."), "Blue", true);
						return;
					}

					const section = frm.dashboard.add_section("", __("Stock Levels"));

					// sort by qty
					r.message.sort(function (a, b) {
						return a.qty > b.qty ? 1 : -1;
					});

					const rows = $("<div></div>").appendTo(section);
					const uom_str = frm.doc.stock_uom ? ` ${frm.doc.stock_uom}` : "";

					// show
					(r.message || []).forEach(function (d) {
						if (d.qty != 0) {
							$(`<div class='row' style='margin-bottom: 10px;'>
								<div class='col-sm-3 small' style='padding-top: 3px;'>${d.warehouse}</div>
								<div class='col-sm-3 small text-right' style='padding-top: 3px;'>${d.qty}${uom_str}</div>
								<div class='col-sm-6'>
									<button class='btn btn-default btn-xs btn-move' style='margin-right: 7px;'
										data-qty = "${d.qty}"
										data-warehouse = "${d.warehouse}">
										${__("Move")}</button>
									<button class='btn btn-default btn-xs btn-split'
										data-qty = "${d.qty}"
										data-warehouse = "${d.warehouse}">
										${__("Split")}</button>
								</div>
							</div>`).appendTo(rows);
						}
					});

					// move - ask for target warehouse and make stock entry
					rows.find(".btn-move").on("click", function () {
						const $btn = $(this);
						const fields = [
							{
								fieldname: "to_warehouse",
								label: __("To Warehouse"),
								fieldtype: "Link",
								options: "Warehouse",
							},
						];

						frappe.prompt(
							fields,
							function (data) {
								frappe.call({
									method: "erpnext.stock.doctype.stock_entry.stock_entry_utils.make_stock_entry",
									args: {
										item_code: frm.doc.item,
										batch_no: frm.doc.name,
										qty: $btn.attr("data-qty"),
										from_warehouse: $btn.attr("data-warehouse"),
										to_warehouse: data.to_warehouse,
										source_document: frm.doc.reference_name,
										reference_doctype: frm.doc.reference_doctype,
									},
									callback: function (r) {
										frappe.show_alert(
											__("Stock Entry {0} created", [
												'<a href="/app/stock-entry/' +
													r.message.name +
													'">' +
													r.message.name +
													"</a>",
											])
										);
										frm.refresh();
									},
								});
							},
							__("Select Target Warehouse"),
							__("Move")
						);
					});

					// split - ask for new qty and batch ID (optional)
					rows.find(".btn-split").on("click", function () {
						const $btn = $(this);
						frappe.prompt(
							[
								{
									fieldname: "qty",
									label: __("New Batch Qty"),
									fieldtype: "Float",
									default: $btn.attr("data-qty"),
								},
								{
									fieldname: "new_batch_id",
									label: __("New Batch ID (Optional)"),
									fieldtype: "Data",
								},
							],
							function (data) {
								frappe
									.xcall("erpnext.stock.doctype.batch.batch.split_batch", {
										item_code: frm.doc.item,
										batch_no: frm.doc.name,
										qty: data.qty,
										warehouse: $btn.attr("data-warehouse"),
										new_batch_id: data.new_batch_id,
									})
									.then(function () { frm.reload_doc(); });
							},
							__("Split Batch"),
							__("Split")
						);
					});

					frm.dashboard.show();
				},
			});
		}
	},
});

function set_batch_uom_from_item(frm) {
	if (!frm.doc.item) return;

	frappe.db.get_value(
		"Item",
		frm.doc.item,
		["custom_default_uom_warehouse", "stock_uom"],
		function (r) {
			if (r) {
				var target_uom = r.custom_default_uom_warehouse || r.stock_uom;
				if (target_uom && frm.doc.stock_uom !== target_uom) {
					frm.set_value("stock_uom", target_uom);
				}
				if (r.custom_default_uom_warehouse && frm.fields_dict.custom_default_uom_warehouse) {
					frm.set_value("custom_default_uom_warehouse", r.custom_default_uom_warehouse);
				}
			}
		}
	);
}

function update_warehouse_qty(frm) {
	if (!frm.doc.item) return;

	frappe.db.get_value(
		"Item",
		frm.doc.item,
		["stock_uom", "custom_default_uom_warehouse"],
		function (r) {
			if (!r) return;
			let warehouse_uom = frm.doc.stock_uom || r.custom_default_uom_warehouse;
			if (warehouse_uom && r.stock_uom && warehouse_uom !== r.stock_uom) {
				frappe.call({
					method: "warehouse_app.overrides.batch_uom.get_item_uom_conversion_factor",
					args: { item_code: frm.doc.item, uom: warehouse_uom },
					callback: function (r) {
						let cf_res = r.message;
						if (cf_res && cf_res.conversion_factor) {
							let cf = flt(cf_res.conversion_factor);
							if (frm.fields_dict.custom_uom_conversion_factor) {
								frm.set_value("custom_uom_conversion_factor", cf);
							}
							if (frm.fields_dict.custom_qty_in_uom && frm.doc.batch_qty != null) {
								frm.set_value("custom_qty_in_uom", frm.doc.batch_qty);
							}
						}
					},
				});
			}
		}
	);
}
