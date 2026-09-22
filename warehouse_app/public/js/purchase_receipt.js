frappe.ui.form.on("Purchase Receipt", {
	refresh: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Print Label"), function () {
				open_print_label_dialog(frm);
			});
		}
	},
	on_submit: function (frm) {
		setTimeout(function () {
			open_print_label_dialog(frm);
		}, 600);
	}
});

// Request item details for printing labels
function open_print_label_dialog(frm) {
	frappe.call({
		method: "warehouse_app.overrides.purchase_receipt.get_purchase_receipt_label_data",
		args: {
			purchase_receipt_name: frm.doc.name
		},
		freeze: true,
		freeze_message: __("Memuat data item label..."),
		callback: function (r) {
			if (!r.message || !r.message.items || r.message.items.length === 0) {
				frappe.msgprint(__("Tidak ada item ditemukan pada Purchase Receipt ini."));
				return;
			}
			render_dialog(frm, r.message);
		}
	});
}

// Render label modal with child table grid layout
function render_dialog(frm, data) {
	let items = data.items.map(function (it, idx) {
		let actual_qty = Math.max(1, parseInt(it.actual_qty || it.qty) || 1);
		return {
			id: "row_" + frappe.utils.get_random(6),
			item_key: it.name || (it.item_code + "_" + idx),
			item_code: it.item_code || "",
			item_name: it.item_name || "",
			actual_qty: actual_qty,
			qty: actual_qty,
			receipt_date: it.receipt_date || data.receipt_date || "",
			expiry_date: it.expiry_date || "",
			selected: true
		};
	});

	let dialog = new frappe.ui.Dialog({
		title: __("Cetak Label Item"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "label_instructions",
				options: '<div style="margin-bottom:12px;font-size:13px;color:var(--text-muted);">'
					+ __("Sesuaikan jumlah quantity (lembar label) dan tanggal EXP. Gunakan tombol duplikat untuk mencetak variasi tanggal.")
					+ '</div>'
			},
			{
				fieldtype: "HTML",
				fieldname: "label_items_table"
			}
		],
		primary_action_label: __("Print"),
		primary_action: function () {
			let current_items = get_table_data(dialog);
			if (current_items.length === 0) {
				frappe.msgprint(__("Minimal harus ada 1 item yang dipilih untuk dicetak."));
				return;
			}

			let missing_exp = [];
			dialog.$wrapper.find("#label-table-body tr").each(function (idx) {
				let row_id = $(this).data("id");
				let found = items.find(function (i) { return i.id === row_id; });
				if (found && found.selected) {
					let $input = $(this).find(".row-exp-date");
					let exp_val = ($input.val() !== undefined && $input.val() !== null) ? $input.val().trim() : (found.expiry_date || "").trim();
					if (!exp_val) {
						missing_exp.push({
							row_num: idx + 1,
							item_code: found.item_code,
							$input: $input
						});
					}
				}
			});

			if (missing_exp.length > 0) {
				dialog.$wrapper.find(".row-exp-date").css("border-color", "");
				missing_exp.forEach(function (m) {
					m.$input.css("border-color", "var(--red-500, #ff5858)");
				});
				missing_exp[0].$input.focus();

				let missing_desc = missing_exp.map(function (m) {
					return __("Baris {0} ({1})", [m.row_num, frappe.utils.escape_html(m.item_code)]);
				}).join(", ");

				frappe.msgprint({
					title: __("Peringatan"),
					message: __("Tanggal EXP (Expiry Date) wajib diisi sebelum mencetak label.<br>Item yang belum memiliki tanggal EXP: <b>{0}</b>", [missing_desc]),
					indicator: "orange"
				});
				return;
			}

			// Validasi Total Quantity per item tidak boleh melebihi aktual qty
			let exceeded_items = [];
			let item_totals = {};
			items.forEach(function (it) {
				if (!it.selected) return;
				let key = it.item_key || it.item_code;
				if (!item_totals[key]) {
					item_totals[key] = {
						item_code: it.item_code,
						actual_qty: it.actual_qty || 0,
						total_qty: 0,
						rows: []
					};
				}
				item_totals[key].total_qty += (parseInt(it.qty) || 0);
				item_totals[key].rows.push(it.id);
			});

			Object.keys(item_totals).forEach(function (key) {
				let info = item_totals[key];
				if (info.actual_qty > 0 && info.total_qty > info.actual_qty) {
					exceeded_items.push(info);
				}
			});

			if (exceeded_items.length > 0) {
				exceeded_items.forEach(function (info) {
					info.rows.forEach(function (r_id) {
						dialog.$wrapper.find('tr[data-id="' + r_id + '"] .row-qty').css("border-color", "var(--red-500, #ff5858)");
					});
				});

				let desc = exceeded_items.map(function (e) {
					return __("Item <b>{0}</b>: total print {1} (aktual: {2})", [
						frappe.utils.escape_html(e.item_code),
						e.total_qty,
						e.actual_qty
					]);
				}).join("<br>");

				frappe.msgprint({
					title: __("Peringatan Qty Melebihi Aktual"),
					message: __("Jumlah label yang dicetak tidak boleh melebihi aktual qty:<br>{0}<br><br>Harap sesuaikan kembali jumlah quantity sebelum mencetak.", [desc]),
					indicator: "red"
				});
				return;
			}

			frappe.call({
				method: "warehouse_app.overrides.purchase_receipt.render_labels_html",
				args: { items_json: JSON.stringify(current_items) },
				freeze: true,
				freeze_message: __("Menyiapkan layout cetak label..."),
				callback: function (r) {
					if (r.message) {
						let w = window.open("", "_blank");
						if (!w) {
							frappe.msgprint(__("Popup browser terblokir. Harap izinkan pop-up window."));
							return;
						}
						w.document.open();
						w.document.write(r.message);
						w.document.close();
					}
				}
			});
		}
	});

	let $wrapper = dialog.get_field("label_items_table").$wrapper;

	// Sum total label quantity for active rows
	function total_labels() {
		return items.reduce(function (sum, item) {
			return item.selected ? sum + (parseInt(item.qty) || 1) : sum;
		}, 0);
	}

	// Update total count and row selection summary
	function update_counter() {
		var total = total_labels();
		var selected_count = items.filter(function (i) { return i.selected; }).length;
		$wrapper.find("#total-labels-count").text(total);
		$wrapper.find("#selected-rows-count").text(selected_count + " / " + items.length + " " + __("item dipilih"));
		var all_selected = items.length > 0 && selected_count === items.length;
		$wrapper.find("#check-all-rows").prop("checked", all_selected);
	}

	// Build child table markup matching Frappe grid style
	function build_table() {
		var selected_count = items.filter(function (i) { return i.selected; }).length;
		var all_selected = items.length > 0 && selected_count === items.length;

		var html = '<style>'
			+ '.label-grid-wrapper {'
			+ '  border: 1px solid var(--border-color, #e2e8f0);'
			+ '  border-radius: var(--border-radius-md, 8px);'
			+ '  background-color: var(--card-bg, #ffffff);'
			+ '  overflow: hidden;'
			+ '}'
			+ '.label-grid-table {'
			+ '  width: 100%;'
			+ '  border-collapse: separate;'
			+ '  border-spacing: 0;'
			+ '  font-size: 13px;'
			+ '  margin-bottom: 0;'
			+ '}'
			+ '.label-grid-table th {'
			+ '  background-color: var(--subtle-fg, #f8f9fa);'
			+ '  color: var(--text-muted, #6c757d);'
			+ '  font-size: 12px;'
			+ '  font-weight: 500;'
			+ '  padding: 8px 10px;'
			+ '  border-bottom: 1px solid var(--border-color, #ebeff2);'
			+ '  border-right: 1px solid var(--border-color, #ebeff2);'
			+ '  vertical-align: middle;'
			+ '}'
			+ '.label-grid-table th:last-child {'
			+ '  border-right: none;'
			+ '}'
			+ '.label-grid-table td {'
			+ '  padding: 6px 10px;'
			+ '  border-bottom: 1px solid var(--border-color, #f0f2f5);'
			+ '  border-right: 1px solid var(--border-color, #ebeff2);'
			+ '  vertical-align: middle;'
			+ '}'
			+ '.label-grid-table td:last-child {'
			+ '  border-right: none;'
			+ '}'
			+ '.label-grid-table tbody tr:last-child td {'
			+ '  border-bottom: none;'
			+ '}'
			+ '.label-grid-table tbody tr:hover {'
			+ '  background-color: var(--subtle-accent, #fafbfc);'
			+ '}'
			+ '.label-grid-table input.row-qty {'
			+ '  background-color: transparent !important;'
			+ '}'
			+ '.label-grid-row.row-unselected {'
			+ '  opacity: 0.45;'
			+ '}'
			+ '.label-grid-btn {'
			+ '  background: transparent;'
			+ '  border: none;'
			+ '  padding: 4px 6px;'
			+ '  border-radius: 4px;'
			+ '  cursor: pointer;'
			+ '  color: var(--text-muted, #6c757d);'
			+ '  transition: background-color 0.15s ease, color 0.15s ease;'
			+ '}'
			+ '.label-grid-btn:hover {'
			+ '  background-color: var(--bg-subtle, #f0f2f5);'
			+ '  color: var(--text-color, #1f272e);'
			+ '}'
			+ '.label-grid-btn.btn-delete:hover {'
			+ '  background-color: var(--red-50, #fff1f0);'
			+ '  color: var(--red-500, #ff5858);'
			+ '}'
			+ '</style>'
			+ '<div class="label-grid-wrapper">'
			+ '<div class="table-responsive" style="max-height:420px;overflow-y:auto;">'
			+ '<table class="label-grid-table">'
			+ '<thead>'
			+ '<tr>'
			+ '<th style="width:38px;text-align:center;">'
			+ '<input type="checkbox" id="check-all-rows" ' + (all_selected ? 'checked' : '') + ' style="cursor:pointer;accent-color:var(--primary,#171717);width:14px;height:14px;vertical-align:middle;border-radius:3px;" />'
			+ '</th>'
			+ '<th style="width:42px;text-align:center;">No.</th>'
			+ '<th>' + __("Item Code") + ' <span style="color:var(--red-500,#ff5858);font-weight:700;">*</span></th>'
			+ '<th>' + __("Item Name") + '</th>'
			+ '<th style="width:110px;text-align:right;">' + __("Quantity") + ' <span style="color:var(--red-500,#ff5858);font-weight:700;">*</span></th>'
			+ '<th style="width:150px;text-align:left;">' + __("EXP Date") + ' <span style="color:var(--red-500,#ff5858);font-weight:700;">*</span></th>'
			+ '<th style="width:65px;text-align:center;"><i class="fa fa-cog" style="color:var(--text-muted,#6c757d);opacity:0.6;font-size:13px;"></i></th>'
			+ '</tr>'
			+ '</thead>'
			+ '<tbody id="label-table-body">';

		if (items.length === 0) {
			html += '<tr><td colspan="7" class="text-center py-4 text-muted">'
				+ __("Tidak ada item ditemukan.") + '</td></tr>';
		} else {
			items.forEach(function (item, index) {
				var delete_btn = (index > 0)
					? '<button type="button" class="label-grid-btn btn-delete btn-delete-row" title="' + __("Hapus baris") + '"><i class="fa fa-trash"></i></button>'
					: '';

				var unselected_cls = !item.selected ? ' row-unselected' : '';

				var item_key = item.item_key || item.item_code;
				var other_sum = items
					.filter(function (i) { return (i.item_key || i.item_code) === item_key && i.id !== item.id && i.selected; })
					.reduce(function (sum, i) { return sum + (parseInt(i.qty) || 0); }, 0);
				var max_allowed = Math.max(1, (item.actual_qty || 999999) - other_sum);

				html += '<tr class="label-grid-row' + unselected_cls + '" data-id="' + item.id + '">'
					+ '<td style="text-align:center;">'
					+ '<input type="checkbox" class="row-check" ' + (item.selected ? 'checked' : '') + ' style="cursor:pointer;accent-color:var(--primary,#171717);width:14px;height:14px;vertical-align:middle;" />'
					+ '</td>'
					+ '<td style="text-align:center;color:var(--text-muted,#6c757d);font-size:12px;">' + (index + 1) + '</td>'
					+ '<td style="font-weight:700;color:var(--text-color,#1f272e);">' + frappe.utils.escape_html(item.item_code) + '</td>'
					+ '<td style="color:var(--text-color,#1f272e);">' + frappe.utils.escape_html(item.item_name) + '</td>'
					+ '<td style="text-align:right;">'
					+ '<input type="number" min="1" max="' + max_allowed + '" step="1" class="form-control form-control-sm row-qty" value="' + item.qty + '" style="text-align:right;height:30px;font-size:13px;font-weight:600;border-radius:4px;border:1px solid var(--border-color,#d1d8dd);background-color:transparent !important;padding:4px 8px;" />'
					+ '<div style="font-size:11px;color:var(--text-muted,#6c757d);margin-top:2px;"></div>'
					+ '</td>'
					+ '<td><input type="date" class="form-control form-control-sm row-exp-date" value="' + item.expiry_date + '" style="height:30px;font-size:12px;font-weight:500;border-radius:4px;border:1px solid var(--border-color,#d1d8dd);background-color:transparent !important;padding:4px 8px;" /></td>'
					+ '<td style="text-align:center;">'
					+ '<button type="button" class="label-grid-btn btn-duplicate-row" title="' + __("Duplikat baris") + '" style="margin-right:2px;"><i class="fa fa-copy"></i></button>'
					+ delete_btn
					+ '</td>'
					+ '</tr>';
			});
		}

		html += '</tbody></table></div></div>'
			+ '<div class="d-flex justify-content-between align-items-center mt-2 px-1" style="font-size:12px;">'
			+ '<div>'
			+ '<span class="text-muted">' + __("Total Label yang Dicetak:") + ' </span>'
			+ '<strong id="total-labels-count" style="color:var(--text-color,#1f272e);font-size:13px;">' + total_labels() + '</strong>'
			+ '</div>'
			+ '<div class="text-muted" id="selected-rows-count">'
			+ selected_count + ' / ' + items.length + ' ' + __("item dipilih")
			+ '</div>'
			+ '</div>';

		$wrapper.html(html);

		function update_dynamic_max() {
			items.forEach(function (it) {
				var key = it.item_key || it.item_code;
				var other_sum = items
					.filter(function (i) { return (i.item_key || i.item_code) === key && i.id !== it.id && i.selected; })
					.reduce(function (sum, i) { return sum + (parseInt(i.qty) || 0); }, 0);

				var max_for_it = Math.max(1, (it.actual_qty || 999999) - other_sum);
				$wrapper.find('tr[data-id="' + it.id + '"] .row-qty').attr("max", max_for_it);
			});
		}

		$wrapper.find("#check-all-rows").on("change", function () {
			var is_checked = $(this).is(":checked");
			items.forEach(function (i) { i.selected = is_checked; });
			build_table();
		});

		$wrapper.find(".row-check").on("change", function () {
			var row_id = $(this).closest("tr").data("id");
			var found = items.find(function (i) { return i.id === row_id; });
			if (found) {
				found.selected = $(this).is(":checked");
				if (found.selected) {
					$(this).closest("tr").removeClass("row-unselected");
				} else {
					$(this).closest("tr").addClass("row-unselected");
				}
				update_dynamic_max();
				update_counter();
			}
		});

		$wrapper.find(".row-qty").on("input change", function () {
			var row_id = $(this).closest("tr").data("id");
			var found = items.find(function (i) { return i.id === row_id; });
			if (found) {
				var key = found.item_key || found.item_code;
				var other_sum = items
					.filter(function (i) { return (i.item_key || i.item_code) === key && i.id !== found.id && i.selected; })
					.reduce(function (sum, i) { return sum + (parseInt(i.qty) || 0); }, 0);

				var max_allowed = Math.max(1, (found.actual_qty || 999999) - other_sum);
				var raw_val = $(this).val();
				if (raw_val === "") {
					return;
				}

				var val = parseInt(raw_val);
				if (isNaN(val) || val < 1) {
					val = 1;
				}

				if (val > max_allowed) {
					val = max_allowed;
					$(this).val(val);
					frappe.show_alert({
						message: __("Quantity tidak bisa dinaikkan lagi karena sudah mencapai batas ({0}).", [found.actual_qty]),
						indicator: "orange"
					}, 3);
				}

				found.qty = val;
				update_dynamic_max();
				update_counter();
			}
		});

		$wrapper.find(".row-qty").on("blur", function () {
			var row_id = $(this).closest("tr").data("id");
			var found = items.find(function (i) { return i.id === row_id; });
			if (found) {
				var val = parseInt($(this).val());
				if (isNaN(val) || val < 1) {
					val = 1;
					$(this).val(1);
					found.qty = 1;
					update_dynamic_max();
					update_counter();
				}
			}
		});

		$wrapper.find(".row-exp-date").on("input change", function () {
			var row_id = $(this).closest("tr").data("id");
			var found = items.find(function (i) { return i.id === row_id; });
			if (found) {
				found.expiry_date = $(this).val();
			}
			if ($(this).val()) {
				$(this).css("border-color", "");
			}
		});

		$wrapper.find(".btn-duplicate-row").on("click", function () {
			var row_id = $(this).closest("tr").data("id");
			var idx = items.findIndex(function (i) { return i.id === row_id; });
			if (idx !== -1) {
				var target = items[idx];
				var tr = $(this).closest("tr");

				// Sync all current input values from DOM to items array before duplicating
				$wrapper.find("#label-table-body tr").each(function () {
					var r_id = $(this).data("id");
					var it = items.find(function (i) { return i.id === r_id; });
					if (it) {
						it.qty = Math.max(1, parseInt($(this).find(".row-qty").val()) || it.qty || 1);
						it.expiry_date = $(this).find(".row-exp-date").val() || it.expiry_date;
					}
				});

				var key = target.item_key || target.item_code;
				// Cari baris pertama dari item ini (baris ke satu)
				var first_row = items.find(function (i) { return (i.item_key || i.item_code) === key; });

				if (!first_row || first_row.qty <= 1) {
					frappe.show_alert({
						message: __("Tidak bisa menduplikasi lagi, baris pertama item {0} sudah mencapai batas minimal (1).", [target.item_code]),
						indicator: "orange"
					}, 3);
					return;
				}

				// Kurangi 1 terus untuk baris ke satu
				first_row.qty = first_row.qty - 1;

				var clone = {
					id: "row_" + frappe.utils.get_random(6),
					item_key: target.item_key,
					item_code: target.item_code,
					item_name: target.item_name,
					actual_qty: target.actual_qty,
					qty: 1,
					receipt_date: target.receipt_date || data.receipt_date || "",
					expiry_date: tr.find(".row-exp-date").val() || target.expiry_date,
					selected: true
				};

				items.splice(idx + 1, 0, clone);
				build_table();
			}
		});

		$wrapper.find(".btn-delete-row").on("click", function () {
			var row_id = $(this).closest("tr").data("id");
			var del_item = items.find(function (i) { return i.id === row_id; });
			if (del_item) {
				// Sync current values first
				$wrapper.find("#label-table-body tr").each(function () {
					var r_id = $(this).data("id");
					var it = items.find(function (i) { return i.id === r_id; });
					if (it) {
						it.qty = Math.max(1, parseInt($(this).find(".row-qty").val()) || it.qty || 1);
						it.expiry_date = $(this).find(".row-exp-date").val() || it.expiry_date;
					}
				});

				var key = del_item.item_key || del_item.item_code;
				items = items.filter(function (i) { return i.id !== row_id; });

				// Kembalikan qty baris yang dihapus ke baris ke satu
				var first_row = items.find(function (i) { return (i.item_key || i.item_code) === key; });
				if (first_row) {
					first_row.qty = (first_row.qty || 1) + (del_item.qty || 1);
				}
			}
			build_table();
		});
	}

	// Collect active item entries for printing
	function get_table_data(d) {
		var result = [];
		d.$wrapper.find("#label-table-body tr").each(function () {
			var row_id = $(this).data("id");
			if (!row_id) return;
			var found = items.find(function (i) { return i.id === row_id; });
			if (found && found.selected) {
				var exp_val = $(this).find(".row-exp-date").val();
				if (exp_val === undefined || exp_val === null) {
					exp_val = found.expiry_date || "";
				}
				result.push({
					item_key: found.item_key,
					item_code: found.item_code,
					item_name: found.item_name,
					actual_qty: found.actual_qty,
					qty: Math.max(1, parseInt($(this).find(".row-qty").val()) || found.qty || 1),
					receipt_date: found.receipt_date || data.receipt_date || "",
					expiry_date: exp_val.trim()
				});
			}
		});
		return result;
	}

	build_table();
	dialog.show();
}

frappe.ui.form.on("Purchase Receipt Item", {
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