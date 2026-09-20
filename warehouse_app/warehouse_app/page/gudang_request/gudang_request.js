// W9: request serah terima ala-gudang. UI bicara bahasa gudang
// (adonan ke + nama item); pembuatan/pembatalan MR memanggil endpoint
// production_app (create_request/cancel_request) — satu penulis ringkasan
// WO, pola sama dengan aksi papan W4 yang memanggil mapper native erpnext.
// Validasi box (kg + jumlah, harus tepat expected units) andalkan server:
// atomic, fail-honest, pesan errornya langsung tampil sebagai toast.

frappe.pages['gudang_request'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Request Serah Terima'),
		single_column: true,
	});

	const $main = $(wrapper).find('.layout-main');
	$main.html(`
		<div class="wzrq-toolbar">
			<input class="form-control wzrq-search" type="text"
				placeholder="${__('Cari adonan / nama item / nomor WO...')}" />
			<button class="btn btn-default wzrq-refresh">${__('Muat Ulang')}</button>
		</div>
		<div class="wzrq-list"></div>
		<div class="wzrq-empty text-muted" style="display:none">
			${__('Tidak ada Work Order yang bisa diminta.')}
		</div>
	`);

	const $search = $main.find('.wzrq-search');
	const $list = $main.find('.wzrq-list');
	const $empty = $main.find('.wzrq-empty');

	function esc(value) {
		return frappe.utils.escape_html(value == null ? '' : String(value));
	}

	function row_html(r) {
		const adonan = r.custom_adonan_ke ? esc(r.custom_adonan_ke) : '-';
		const badge = r.request_active
			? `<span class="badge badge-warning wzrq-badge">${__('Diminta')} (${esc(r.custom_handover_material_request)})</span>`
			: '';
		const action = r.request_active
			? `<button class="btn btn-xs btn-secondary wzrq-cancel" data-mr="${esc(r.custom_handover_material_request)}">${__('Batalkan')}</button>`
			: `<button class="btn btn-xs btn-primary wzrq-request" data-wo="${esc(r.name)}">${__('Request')}</button>`;
		return `
			<div class="wzrq-card">
				<div class="wzrq-card-main">
					<div class="wzrq-title">${__('Adonan')} <b>${adonan}</b> — ${esc(r.item_name)}</div>
					<div class="wzrq-sub text-muted">
						${esc(r.name)} • ${r.produced_qty} ${esc(r.stock_uom)} • ${esc(r.status)}
						${badge}
					</div>
				</div>
				<div class="wzrq-actions">${action}</div>
			</div>`;
	}

	function load(search) {
		frappe.call({
			method: 'warehouse_app.warehouse_app.gudang_request.requestable_work_orders',
			args: { search: search || '' },
			freeze: true,
			freeze_message: __('Memuat Work Order...'),
		}).then((r) => {
			const rows = (r.message && r.message.length && r.message) || [];
			$list.html(rows.map(row_html).join(''));
			$empty.toggle(rows.length === 0);
		});
	}

	$main.on('click', '.wzrq-request', function () {
		request_dialog($(this).attr('data-wo'), load);
	});

	$main.on('click', '.wzrq-cancel', function () {
		cancel_request($(this).attr('data-mr'), load);
	});

	$search.on('keydown', (e) => {
		if (e.which === frappe.ui.keyCode.ENTER) {
			load($search.val());
		}
	});
	$main.find('.wzrq-refresh').on('click', () => load($search.val()));

	load();
};

// P2 review W9: muat ulang tiap kali halaman tampil lagi, supaya badge
// "Diminta" tidak basi setelah navigasi pergi-pulang.
frappe.pages['gudang_request'].on_page_show = function (wrapper) {
	const $search = $(wrapper).find('.wzrq-search');
	if ($search.length) {
		frappe.call({
			method: 'warehouse_app.warehouse_app.gudang_request.requestable_work_orders',
			args: { search: $search.val() || '' },
		}).then((r) => {
			const rows = (r.message && r.message.length && r.message) || [];
			$(wrapper).find('.wzrq-list').html(rows.map(row_html).join(''));
			$(wrapper).find('.wzrq-empty').toggle(rows.length === 0);
		});
	}
};

function request_dialog(work_order, done) {
	frappe.prompt(
		[
			{ fieldname: 'sec1', fieldtype: 'Section Break', label: __('Box 1') },
			{ fieldname: 'box_1', fieldtype: 'Float', label: __('Berat (kg)'), reqd: 1, default: 0 },
			{ fieldname: 'box_1_qty', fieldtype: 'Int', label: __('Jumlah'), reqd: 1, default: 0 },
			{ fieldname: 'sec2', fieldtype: 'Section Break', label: __('Box 2 (kosongkan bila tidak ada)') },
			{ fieldname: 'box_2', fieldtype: 'Float', label: __('Berat (kg)'), default: 0 },
			{ fieldname: 'box_2_qty', fieldtype: 'Int', label: __('Jumlah'), default: 0 },
		],
		(values) => {
			frappe.call({
				method: 'production_app.api.handover.create_request',
				args: {
					work_order: work_order,
					box_1: values.box_1,
					box_1_qty: values.box_1_qty,
					box_2: values.box_2 || 0,
					box_2_qty: values.box_2_qty || 0,
				},
				freeze: true,
				freeze_message: __('Membuat request serah terima...'),
			}).then((r) => {
				frappe.show_alert({
					message: __('Request {0} dibuat', [r.message.material_request]),
					indicator: 'green',
				});
				done && done();
			});
		},
		__('Alokasi Box untuk {0}', [work_order]),
		__('Buat Request')
	);
}

function cancel_request(material_request, done) {
	frappe.confirm(__('Batalkan request {0} yang belum terkirim?', [material_request]), () => {
		frappe.call({
			method: 'production_app.api.handover.cancel_request',
			args: { material_request: material_request },
			freeze: true,
			freeze_message: __('Membatalkan request...'),
		}).then(() => {
			frappe.show_alert({ message: __('Request dibatalkan'), indicator: 'orange' });
			done && done();
		});
	});
}
