// W9: request serah terima ala-gudang. UI bicara bahasa gudang
// (adonan ke + nama item); pembuatan/pembatalan MR memanggil endpoint
// production_app (create_request/cancel_request) — satu penulis ringkasan
// WO, pola sama dengan aksi papan W4 yang memanggil mapper native erpnext.
// Validasi box (kg + jumlah, harus tepat expected units) andalkan server:
// atomic, fail-honest, pesan errornya langsung tampil sebagai toast.
//
// Revisi umpan balik user: tampilan tabel + checklist — pilih satu atau
// beberapa WO sekaligus, lalu satu aksi "Buat Request" (dialog alokasi Box
// per baris, prefilled jumlah = hasil WO).

frappe.pages['gudang_request'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Request Serah Terima'),
		single_column: true,
	});

	const $main = $(wrapper).find('.layout-main');
	// .layout-main Desk v16 = flex row: semua konten wajib dibungkus SATU
	// root full-width agar tidak menjadi kolom di samping tabel.
	$main.html(`
		<div class="wzrq-root">
		<div class="wzrq-toolbar">
			<input class="form-control wzrq-search" type="text"
				placeholder="${__('Cari adonan / nama item / nomor WO...')}" />
			<button class="btn btn-default wzrq-refresh">${__('Muat Ulang')}</button>
			<div class="wzrq-bulk">
				<span class="wzrq-bulk-count text-muted"></span>
				<button class="btn btn-primary btn-sm wzrq-bulk-request" disabled>${__('Buat Request')}</button>
				<button class="btn btn-default btn-sm wzrq-bulk-clear" style="display:none">${__('Kosongkan')}</button>
			</div>
		</div>
		<div class="wzrq-table-wrap">
			<table class="wzrq-table">
				<thead>
					<tr>
						<th class="wzrq-col-check"><input type="checkbox" class="wzrq-check-all" aria-label="${__('Pilih semua')}" /></th>
						<th class="wzrq-col-adonan">${__('Adonan')}</th>
						<th>${__('Item')}</th>
						<th class="wzrq-col-qty">${__('Hasil')}</th>
						<th class="wzrq-col-wo">${__('Work Order')}</th>
						<th class="wzrq-col-status">${__('Status')}</th>
						<th class="wzrq-col-aksi"></th>
					</tr>
				</thead>
				<tbody></tbody>
			</table>
			<div class="wzrq-empty text-muted" style="display:none">
				${__('Tidak ada Work Order yang bisa diminta.')}
			</div>
			<div class="wzrq-limit text-muted" style="display:none">
				${__('Menampilkan 50 Work Order terbaru — gunakan pencarian untuk mempersempit.')}
			</div>
		</div>
		<button class="btn btn-default wzrq-tweak-btn" title="${__('Pengaturan tampilan')}">
			<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
		</button>
		<div class="wzrq-tweak-panel" style="display:none">
			<div class="wzrq-tweak-label">${__('Kepadatan')}</div>
			<div class="btn-group wzrq-density" role="group">
				<button class="btn btn-default btn-sm wzrq-den-comfort">${__('Nyaman')}</button>
				<button class="btn btn-default btn-sm wzrq-den-compact">${__('Padat')}</button>
			</div>
		</div>
		</div>
	`);

	const $main_page = $(wrapper);
	const $search = $main.find('.wzrq-search');
	const selected = new Set();

	function current_search() {
		return $search.val() || '';
	}

	function load(search) {
		frappe.call({
			method: 'warehouse_app.warehouse_app.gudang_request.requestable_work_orders',
			args: { search: search || '' },
			freeze: true,
			freeze_message: __('Memuat Work Order...'),
		}).then((r) => {
			wzrq_render($main_page, (r.message && r.message.length && r.message) || []);
		});
	}

	function reload() {
		selected.clear();
		load(current_search());
	}

	// --- interaksi tabel ---
	$main.on('click', '.wzrq-check', function (e) {
		e.stopPropagation();
		const wo = $(this).closest('tr').attr('data-wo');
		if (this.checked) {
			selected.add(wo);
		} else {
			selected.delete(wo);
		}
		wzrq_update_bulk($main_page, selected);
	});

	$main.on('click', '.wzrq-row', function (e) {
		if ($(e.target).closest('button, input, a').length) {
			return;
		}
		const wo = $(this).attr('data-wo');
		if (!wzrq_rows($main_page).some((r) => r.name === wo && !r.request_active)) {
			return;
		}
		if (selected.has(wo)) {
			selected.delete(wo);
		} else {
			selected.add(wo);
		}
		$(this).find('.wzrq-check').prop('checked', selected.has(wo));
		wzrq_update_bulk($main_page, selected);
	});

	$main.on('click', '.wzrq-cancel', function () {
		cancel_request($(this).attr('data-mr'), reload);
	});

	$main.on('change', '.wzrq-check-all', function () {
		const rows = wzrq_rows($main_page).filter((r) => !r.request_active);
		rows.forEach((r) => (this.checked ? selected.add(r.name) : selected.delete(r.name)));
		$main.find('.wzrq-row').each(function () {
			$(this).find('.wzrq-check').prop('checked', selected.has($(this).attr('data-wo')));
		});
		wzrq_update_bulk($main_page, selected);
	});

	// --- aksi massal ---
	$main.on('click', '.wzrq-bulk-request', () => {
		const wos = wzrq_rows($main_page).filter((r) => selected.has(r.name));
		if (wos.length) {
			bulk_dialog(wos, reload);
		}
	});

	$main.on('click', '.wzrq-bulk-clear', () => {
		selected.clear();
		$main.find('.wzrq-check').prop('checked', false);
		wzrq_update_bulk($main_page, selected);
	});

	$search.on('keydown', (e) => {
		// frappe.ui.keyCode tidak ada di v16 — pakai kode Enter standar.
		if (e.which === 13 || e.key === 'Enter') {
			load(current_search());
		}
	});
	$main.find('.wzrq-refresh').on('click', () => load(current_search()));

	// --- panel tampilan (kepadatan) ---
	const $panel = $main.find('.wzrq-tweak-panel');
	$main.find('.wzrq-tweak-btn').on('click', () => $panel.toggle());
	function apply_density(mode) {
		$main.toggleClass('wzrq-compact', mode === 'compact');
		$main.find('.wzrq-den-comfort').toggleClass('btn-primary', mode !== 'compact');
		$main.find('.wzrq-den-compact').toggleClass('btn-primary', mode === 'compact');
		try {
			localStorage.setItem('wzrq_density', mode);
		} catch (e) {
			/* private mode: abaikan */
		}
	}
	$main.find('.wzrq-den-comfort').on('click', () => apply_density('comfort'));
	$main.find('.wzrq-den-compact').on('click', () => apply_density('compact'));
	let density = 'comfort';
	try {
		density = localStorage.getItem('wzrq_density') || 'comfort';
	} catch (e) {
		/* default */
	}
	apply_density(density);

	load();
};

// P2 review W9: muat ulang tiap kali halaman tampil lagi, supaya badge
// "Diminta" tidak basi setelah navigasi pergi-pulang.
frappe.pages['gudang_request'].on_page_show = function (wrapper) {
	const $search = $(wrapper).find('.wzrq-search');
	if (!$search.length) {
		return;
	}
	frappe.call({
		method: 'warehouse_app.warehouse_app.gudang_request.requestable_work_orders',
		args: { search: $search.val() || '' },
	}).then((r) => {
		wzrq_render($(wrapper), (r.message && r.message.length && r.message) || []);
	});
};

// ---------------- helpers render (global: dipakai on_page_load & on_page_show)

function wzrq_rows($scope) {
	return $scope.data('wzrq_rows') || [];
}

function wzrq_render($scope, rows) {
	$scope.data('wzrq_rows', rows);
	const $main = $scope.find('.layout-main');
	$main.find('.wzrq-table tbody').html(rows.map(wzrq_row_html).join(''));
	$main.find('.wzrq-empty').toggle(rows.length === 0);
	$main.find('.wzrq-limit').toggle(rows.length >= 50);
	wzrq_update_bulk($scope, new Set());
}

function wzrq_update_bulk($scope, selected) {
	const rows = wzrq_rows($scope);
	const selectable = rows.filter((r) => !r.request_active);
	const n = selectable.filter((r) => selected.has(r.name)).length;
	const $main = $scope.find('.layout-main');
	$main.find('.wzrq-bulk-count').text(n ? __('{0} dipilih', [n]) : '');
	$main.find('.wzrq-bulk-request').prop('disabled', !n);
	$main.find('.wzrq-bulk-request').text(n ? __('Buat Request ({0})', [n]) : __('Buat Request'));
	$main.find('.wzrq-bulk-clear').toggle(n > 0);
	$main
		.find('.wzrq-check-all')
		.prop('checked', selectable.length > 0 && n >= selectable.length)
		.prop('indeterminate', n > 0 && n < selectable.length);
}

function wzrq_esc(value) {
	return frappe.utils.escape_html(value == null ? '' : String(value));
}

function wzrq_row_html(r) {
	const active = r.request_active;
	const status = active
		? `<span class="indicator orange">${__('Diminta')} ${wzrq_esc(r.custom_handover_material_request)}</span>`
		: `<span class="text-muted">${wzrq_esc(r.status)}</span>`;
	const aksi = active
		? `<button class="btn btn-xs btn-default wzrq-cancel" data-mr="${wzrq_esc(r.custom_handover_material_request)}">${__('Batalkan')}</button>`
		: '';
	return `
		<tr class="wzrq-row${active ? ' is-active' : ''}" data-wo="${wzrq_esc(r.name)}">
			<td class="wzrq-col-check"><input type="checkbox" class="wzrq-check"${active ? ' disabled' : ''} aria-label="${wzrq_esc(r.name)}" /></td>
			<td class="wzrq-col-adonan"><span class="wzrq-adonan">${r.custom_adonan_ke ? wzrq_esc(r.custom_adonan_ke) : '—'}</span></td>
			<td class="wzrq-col-item">${wzrq_esc(r.item_name)}</td>
			<td class="wzrq-col-qty">${Number(r.produced_qty || 0).toLocaleString('id-ID')} <span class="text-muted">${wzrq_esc(r.stock_uom)}</span></td>
			<td class="wzrq-col-wo">${wzrq_esc(r.name)}</td>
			<td class="wzrq-col-status">${status}</td>
			<td class="wzrq-col-aksi">${aksi}</td>
		</tr>`;
}

// ---------------- aksi

// Dialog alokasi Box untuk N WO terpilih: satu baris per WO, prefilled
// jumlah Box 1 = hasil WO (server tetap validator kebenaran — atomic).
function bulk_dialog(wos, done) {
	const rows_html = wos
		.map(
			(r) => `
			<tr data-wo="${wzrq_esc(r.name)}">
				<td class="wzrq-dt-wo">
					<div>${__('Adonan')} <b>${wzrq_esc(r.custom_adonan_ke || '-')}</b> — ${wzrq_esc(r.item_name)}</div>
					<div class="text-muted">${wzrq_esc(r.name)} • ${Number(r.produced_qty || 0).toLocaleString('id-ID')} ${wzrq_esc(r.stock_uom)}</div>
				</td>
				<td><input type="number" class="form-control wzrq-kg1" min="0" step="0.01" placeholder="kg" /></td>
				<td><input type="number" class="form-control wzrq-qty1" min="0" step="1" value="${Number(r.produced_qty || 0)}" /></td>
				<td><input type="number" class="form-control wzrq-kg2" min="0" step="0.01" placeholder="kg" /></td>
				<td><input type="number" class="form-control wzrq-qty2" min="0" step="1" value="0" /></td>
			</tr>`
		)
		.join('');

	const d = new frappe.ui.Dialog({
		title: __('Alokasi Box — {0} Work Order', [wos.length]),
		size: 'large',
	});
	d.$body.html(`
		<p class="text-muted">${__('Isi berat (kg) tiap box; jumlah sudah diisi hasil WO. Server memvalidasi kecocokan per Work Order.')}</p>
		<table class="wzrq-dtable">
			<thead>
				<tr>
					<th>${__('Work Order')}</th>
					<th>${__('Box 1 — kg')}</th>
					<th>${__('Box 1 — isi')}</th>
					<th>${__('Box 2 — kg')}</th>
					<th>${__('Box 2 — isi')}</th>
				</tr>
			</thead>
			<tbody>${rows_html}</tbody>
		</table>
	`);

	d.set_primary_action(__('Buat Request'), () => submit_bulk(d, done));
	d.show();
}

async function submit_bulk(d, done) {
	const payloads = [];
	let invalid = null;
	d.$body.find('.wzrq-dtable tbody tr').each(function () {
		if (invalid) {
			return;
		}
		const $tr = $(this);
		const kg1 = $tr.find('.wzrq-kg1').val();
		const q1 = $tr.find('.wzrq-qty1').val();
		const kg2 = $tr.find('.wzrq-kg2').val();
		const q2 = $tr.find('.wzrq-qty2').val() || '0';
		if (kg1 === '' || kg1 === null || q1 === '' || q1 === null) {
			invalid = $tr.attr('data-wo');
			return;
		}
		payloads.push({
			work_order: $tr.attr('data-wo'),
			box_1: parseFloat(kg1),
			box_1_qty: parseInt(q1, 10),
			box_2: kg2 === '' || kg2 === null ? 0 : parseFloat(kg2),
			box_2_qty: parseInt(q2, 10) || 0,
		});
	});
	if (invalid) {
		frappe.msgprint({
			title: __('Data belum lengkap'),
			indicator: 'red',
			message: __('Isi Box 1 (kg dan jumlah) untuk semua baris — periksa {0}.', [invalid]),
		});
		return;
	}

	frappe.freeze(__('Membuat request serah terima...'));
	const ok_list = [];
	const fail_list = [];
	for (const p of payloads) {
		try {
			const r = await frappe.call({
				method: 'production_app.api.handover.create_request',
				args: p,
			});
			ok_list.push(`${r.message.material_request} (${p.work_order})`);
		} catch (e) {
			fail_list.push({ wo: p.work_order, error: wzrq_err_text(e) });
		}
	}
	frappe.unfreeze();
	d.hide();

	if (fail_list.length) {
		frappe.msgprint({
			title: ok_list.length ? __('Sebagian berhasil') : __('Semua gagal'),
			indicator: ok_list.length ? 'orange' : 'red',
			message:
				(ok_list.length
					? `<p>${__('Berhasil: {0}', [wzrq_esc(ok_list.join(', '))])}</p>`
					: '') +
				`<p><b>${__('Gagal')}:</b></p><ul>` +
				fail_list
					.map((f) => `<li><b>${wzrq_esc(f.wo)}</b> — ${wzrq_esc(f.error)}</li>`)
					.join('') +
				'</ul>',
		});
	} else {
		frappe.show_alert({
			message: __('{0} request dibuat', [ok_list.length]),
			indicator: 'green',
		});
	}
	done && done();
}

// Pesan error frappe.call bisa berupa Error ber-message, jqXHR dengan
// _server_messages, atau exc (traceback ber-HTML) — rapikan jadi teks polos.
function wzrq_err_text(e) {
	if (!e) {
		return 'Unknown error';
	}
	if (typeof e === 'string') {
		return e;
	}
	if (e.responseJSON) {
		const j = e.responseJSON;
		if (j._server_messages) {
			try {
				const msgs = JSON.parse(j._server_messages);
				const texts = msgs.map((m) => {
					const inner = typeof m === 'string' ? JSON.parse(m) : m;
					return String(inner.message || '').replace(/<[^>]*>/g, '');
				});
				return texts.join(' ');
			} catch (x) {
				/* jatuh ke bawah */
			}
		}
		if (j.exc) {
			return String(j.exc).replace(/<[^>]*>/g, '').trim().split('\n').pop();
		}
		if (j.message) {
			return String(j.message).replace(/<[^>]*>/g, '');
		}
	}
	if (e.message && !/^\[object/.test(e.message)) {
		return String(e.message).replace(/<[^>]*>/g, '');
	}
	return 'HTTP ' + (e.status || '?');
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
