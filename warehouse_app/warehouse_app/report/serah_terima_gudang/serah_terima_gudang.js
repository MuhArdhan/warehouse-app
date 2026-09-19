// Copyright (c) 2026, Muhammad Yusuf Tri Daryanto
// License: MIT

// W4 Fase C — client script papan "Serah Terima Gudang": render + route saja.
// R1/R5: tombol tidak menulis apa pun — hanya membuka mapper native
// make_stock_entry (whitelisted, material_request.py:935-936) lewat
// frappe.model.open_mapped_doc (create_new.js:325-360 → method POST
// frappe.model.mapper.make_mapped_doc). Validasi qty/batch/over-qty tetap
// native saat SE save/submit (material_request.py:424-429). Nol endpoint
// baru, nol doc_events, nol custom field (AGENTS.md).
//
// Kolom "Aksi" didefinisikan server-side di get_columns() serah_terima_gudang.py
// (display-only, tanpa nilai). Injeksi kolom murni dari JS rapuh: hook
// get_datatable_options hanya dipakai pada branch `new window.DataTable`
// (query_report.js:1130-1136), sedangkan refresh berikutnya memakai
// datatable.refresh(data, columns) dengan kolom server saja (query_report.js:
// 1122-1126, 1076) — kolom ekstern JS akan hilang saat filter diganti.

frappe.query_reports["Serah Terima Gudang"] = {
	// Chip status = indikator baku Frappe
	// (frappe/public/scss/common/indicator.scss: .indicator-pill.<color>,
	// palet: green cyan blue orange yellow gray red dst.).
	chip_colors: {
		"Belum Dikirim": "orange",
		Sebagian: "blue",
		Terkirim: "green",
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value; // baris total / data proxy

		if (column.fieldname === "status_papan") {
			const color = this.chip_colors[value] || "gray";
			return `<span class="indicator-pill ${color}">${frappe.utils.escape_html(
				value
			)}</span>`;
		}

		// Kolom Aksi: tombol hanya untuk bucket Belum Dikirim / Sebagian.
		// Baris Terkirim tanpa aksi — penutupan sisa MR lewat Stop MR native
		// (SOP R9), bukan kode.
		if (column.fieldname === "aksi") {
			if (data.status_papan === "Terkirim") return "";
			const mr = frappe.utils.escape_html(cstr(data.material_request));
			return `<button type="button" class="btn btn-xs btn-default w4-buat-se" data-mr="${mr}">${__(
				"Buat Stock Entry"
			)}</button>`;
		}

		return value;
	},

	onload(report) {
		// Klik didelegasikan ke $report: elemen wrapper dibuat sekali di
		// setup_report_wrapper (query_report.js init:43) dan bertahan antar
		// refresh, sementara onload dipanggil ulang tiap refresh_report
		// (query_report.js:410) → namespace + .off mencegah dobel-bind.
		report.$report
			.off("click.w4_buat_se")
			.on("click.w4_buat_se", ".w4-buat-se", function () {
				frappe.model.open_mapped_doc({
					method:
						"erpnext.stock.doctype.material_request.material_request.make_stock_entry",
					source_name: this.getAttribute("data-mr"),
				});
			});
	},
};
