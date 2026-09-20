// W9: request serah terima ala-gudang. UI bicara bahasa gudang
// (adonan ke + nama item); pembuatan/pembatalan MR memanggil endpoint
// production_app (create_request/cancel_request) — satu penulis ringkasan
// WO, pola sama dengan aksi papan W4 yang memanggil mapper native erpnext.
// Validasi box (kg + jumlah, harus tepat expected units) andalkan server:
// atomic, fail-honest, pesan errornya langsung tampil sebagai toast.
//
// Revisi umpan balik user: (1) tabel checklist — pilih satu/beberapa WO,
// satu aksi "Buat Request" (dialog alokasi Box per baris, prefilled jumlah
// = hasil WO); (2) panel filter ala list view ERPNext: baris
// [Field][operator][Nilai] + Tambah Filter — field dibatasi whitelist
// server (filter_fields), field Item virtual dicocokkan via nama/kode item.

// state filter modul-level (satu instance page per sesi)
let WZRQ_FILTERS = []; // [{field, operator, value(array utk between)}]
let WZRQ_FIELD_META = null;
let WZRQ_VISIBLE = null; // key kolom terlihat (persist di localStorage)

frappe.pages['gudang_request'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Handover Requests'),
		single_column: true,
	});

	const $main = $(wrapper).find('.layout-main');
	// .layout-main Desk v16 = flex row: semua konten wajib dibungkus SATU
	// root full-width agar tidak menjadi kolom di samping tabel.
	$main.html(`
		<div class="wzrq-root">
		<div class="wzrq-toolbar">
			<input class="form-control wzrq-search" type="text"
				placeholder="${__('Search batch, item, or work order...')}" />
			<button class="btn btn-default wzrq-filter-btn">
				<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
				${__('Filter')}
				<span class="wzrq-filter-count"></span>
			</button>
			<button class="btn btn-default wzrq-refresh">${__('Refresh')}</button>
			<div class="wzrq-bulk">
				<span class="wzrq-bulk-count text-muted"></span>
				<button class="btn btn-primary wzrq-bulk-request" disabled>${__('Create Request')}</button>
				<button class="btn btn-default wzrq-bulk-clear" style="display:none">${__('Clear')}</button>
			</div>
			<div class="wzrq-filter-pop" style="display:none">
				<div class="wzrq-filter-rows"></div>
				<div class="wzrq-filter-foot">
					<button class="btn btn-link wzrq-filter-add">+ ${__('Add Filter')}</button>
					<button class="btn btn-link text-muted wzrq-filter-clearall">${__('Clear All Filters')}</button>
				</div>
			</div>
		</div>
		<div class="wzrq-table-wrap">
			<table class="wzrq-table">
				<thead>
					<tr>
						<th class="wzrq-col-check"><input type="checkbox" class="wzrq-check-all" aria-label="${__('Select all')}" /></th>
						<th class="wzrq-col-adonan">${__('Batch')}</th>
						<th>${__('Item')}</th>
						<th class="wzrq-col-qty">${__('Qty')}</th>
						<th class="wzrq-col-wo">${__('Work Order')}</th>
						<th class="wzrq-col-status">${__('Status')}</th>
						<th class="wzrq-col-aksi"></th>
					</tr>
				</thead>
				<tbody></tbody>
			</table>
			<div class="wzrq-cols-pop" style="display:none"></div>
			<div class="wzrq-empty text-muted" style="display:none">
				${__('No matching Work Orders. Try a different search or clear the filters.')}
			</div>
			<div class="wzrq-limit text-muted" style="display:none">
				${__('Showing the 50 most recent Work Orders — narrow with search or filters.')}
			</div>
		</div>
		<button class="btn btn-default wzrq-tweak-btn" title="${__('Display settings')}">
			<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
		</button>
		<div class="wzrq-tweak-panel" style="display:none">
			<div class="wzrq-tweak-label">${__('Density')}</div>
			<div class="btn-group wzrq-density" role="group">
				<button class="btn btn-default btn-sm wzrq-den-comfort">${__('Comfort')}</button>
				<button class="btn btn-default btn-sm wzrq-den-compact">${__('Compact')}</button>
			</div>
		</div>
		</div>
	`);

	const $main_page = $(wrapper);
	const $search = $main.find('.wzrq-search');
	const selected = new Set();
	let apply_timer = null;

	function current_search() {
		return $search.val() || '';
	}

	function load() {
		frappe.call({
			method: 'warehouse_app.warehouse_app.gudang_request.requestable_work_orders',
			args: {
				search: current_search(),
				filters: JSON.stringify(active_filters()),
			},
			freeze: true,
			freeze_message: __('Loading Work Orders...'),
		}).then((r) => {
			wzrq_render($main_page, (r.message && r.message.length && r.message) || []);
		});
	}

	function apply_soon() {
		clearTimeout(apply_timer);
		apply_timer = setTimeout(() => {
			wzrq_collect_rows($main_page);
			wzrq_update_filter_count($main_page);
			load();
		}, 300);
	}

	function reload() {
		selected.clear();
		load();
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

	// --- pencarian & filter ---
	$search.on('keydown', (e) => {
		if (e.which === 13 || e.key === 'Enter') {
			load();
		}
	});
	$main.find('.wzrq-refresh').on('click', load);

	const $pop = $main.find('.wzrq-filter-pop');
	$main.find('.wzrq-filter-btn').on('click', function (e) {
		e.stopPropagation();
		wzrq_ensure_meta(() => {
			wzrq_render_filter_rows($main);
			$pop.toggle();
		});
	});
	// JANGAN stopPropagation di $pop — handler ubah/tambah filter terikat
	// delegated dari $main; cukup tutup popover hanya untuk klik di luar.
	$(document).on('click.wzrq', (e) => {
		if (!$(e.target).closest('.wzrq-filter-pop, .wzrq-filter-btn').length) {
			$pop.hide();
		}
		if (!$(e.target).closest('.wzrq-cols-pop, .wzrq-cols-btn').length) {
			$colsPop.hide();
		}
	});

	$main.on('click', '.wzrq-filter-add', () => {
		wzrq_ensure_meta(() => {
			const first_field = Object.keys(WZRQ_FIELD_META)[0];
			WZRQ_FILTERS.push({ field: first_field, operator: WZRQ_FIELD_META[first_field].operators[0], value: '' });
			wzrq_render_filter_rows($main);
		});
	});

	$main.on('click', '.wzrq-filter-clearall', () => {
		WZRQ_FILTERS = [];
		wzrq_render_filter_rows($main);
		wzrq_update_filter_count($main_page);
		load();
	});

	$pop.on('change', '.wzrq-ff', function () {
		wzrq_collect_rows($main);
		const idx = $(this).closest('.wzrq-filter-row').attr('data-idx');
		const meta = WZRQ_FIELD_META[this.value];
		WZRQ_FILTERS[idx].field = this.value;
		WZRQ_FILTERS[idx].operator = meta.operators[0];
		WZRQ_FILTERS[idx].value = '';
		wzrq_render_filter_rows($main);
		apply_soon();
	});

	$pop.on('change input', '.wzrq-fo, .wzrq-fv, .wzrq-fd1, .wzrq-fd2', function () {
		const row = $(this).closest('.wzrq-filter-row');
		const idx = row.attr('data-idx');
		const prev_op = WZRQ_FILTERS[idx].operator;
		WZRQ_FILTERS[idx].operator = row.find('.wzrq-fo').val();
		const $d1 = row.find('.wzrq-fd1');
		if ($d1.length) {
			WZRQ_FILTERS[idx].value = [$d1.val() || '', row.find('.wzrq-fd2').val() || ''];
		} else {
			WZRQ_FILTERS[idx].value = row.find('.wzrq-fv').val() || '';
		}
		// ganti operator pada field Date mengubah bentuk input (between = 2
		// input tanggal) — baris filter perlu dirender ulang
		if (
			WZRQ_FIELD_META[WZRQ_FILTERS[idx].field] &&
			WZRQ_FIELD_META[WZRQ_FILTERS[idx].field].fieldtype === 'Date' &&
			prev_op !== WZRQ_FILTERS[idx].operator
		) {
			wzrq_render_filter_rows($main);
		}
		wzrq_update_filter_count($main_page);
		apply_soon();
	});

	$pop.on('click', '.wzrq-fx', function () {
		WZRQ_FILTERS.splice($(this).closest('.wzrq-filter-row').attr('data-idx'), 1);
		wzrq_render_filter_rows($main);
		wzrq_update_filter_count($main_page);
		load();
	});

	// --- pilih kolom tabel (ala list view ERPNext) ---
	const $colsPop = $main.find('.wzrq-cols-pop');
	function wzrq_build_cols_pop() {
		const visible = wzrq_visible_columns();
		$colsPop.html(
			`<div class="wzrq-cols-title">${__('Choose columns')}</div>` +
				WZRQ_ALL_COLUMNS.map(
					(c) =>
						`<label class="wzrq-cols-item"><input type="checkbox" class="wzrq-col-toggle" value="${c.key}"${visible.includes(c.key) ? ' checked' : ''} /> ${c.label}</label>`
				).join(''),
		);
	}
	$main.on('click', '.wzrq-cols-btn', function (e) {
		e.stopPropagation();
		wzrq_build_cols_pop();
		$colsPop.toggle();
	});
	$colsPop.on('change', '.wzrq-col-toggle', () => {
		const checked = $colsPop
			.find('.wzrq-col-toggle:checked')
			.map(function () {
				return this.value;
			})
			.get();
		wzrq_set_visible_columns(checked);
		// render ulang tanpa fetch — data baris masih ada di scope
		wzrq_render($main_page, wzrq_rows($main_page));
	});

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
	const $scope = $(wrapper);
	if (!$scope.find('.wzrq-search').length) {
		return;
	}
	frappe.call({
		method: 'warehouse_app.warehouse_app.gudang_request.requestable_work_orders',
		args: {
			search: $scope.find('.wzrq-search').val() || '',
			filters: JSON.stringify(active_filters()),
		},
	}).then((r) => {
		wzrq_render($scope, (r.message && r.message.length && r.message) || []);
	});
};

// ---------------- filter ala list view ERPNext

function active_filters() {
	return WZRQ_FILTERS.filter((f) => {
		if (Array.isArray(f.value)) {
			return f.value.some((x) => String(x || '').trim() !== '');
		}
		return String(f.value || '').trim() !== '';
	});
}

function wzrq_ensure_meta(done) {
	if (WZRQ_FIELD_META) {
		done && done();
		return;
	}
	frappe
		.call({ method: 'warehouse_app.warehouse_app.gudang_request.filter_fields' })
		.then((r) => {
			WZRQ_FIELD_META = r.message || {};
			done && done();
		});
}

function wzrq_render_filter_rows($main) {
	const $rows = $main.find('.wzrq-filter-rows');
	if (!WZRQ_FILTERS.length) {
		$rows.html(`<div class="text-muted wzrq-filter-none">${__('No filters')}</div>`);
		return;
	}
	$rows.html(
		WZRQ_FILTERS.map((f, i) => {
			const meta = WZRQ_FIELD_META[f.field] || { operators: ['like'], fieldtype: 'Data' };
			const field_opts = Object.keys(WZRQ_FIELD_META)
				.map((fname) => `<option value="${wzrq_esc(fname)}"${fname === f.field ? ' selected' : ''}>${wzrq_esc(WZRQ_FIELD_META[fname].label)}</option>`)
				.join('');
			const op_opts = meta.operators
				.map((op) => `<option value="${wzrq_esc(op)}"${op === f.operator ? ' selected' : ''}>${wzrq_esc(wzrq_op_label(op))}</option>`)
				.join('');
			let value_ctl;
			if (meta.fieldtype === 'Date' && f.operator === 'between') {
				const parts = Array.isArray(f.value) ? f.value : String(f.value || '').split(',');
				value_ctl = `<div class="wzrq-fv wzrq-fv-range"><input type="date" class="form-control wzrq-fd1" value="${wzrq_esc(parts[0] || '')}" /><span class="wzrq-fdash">–</span><input type="date" class="form-control wzrq-fd2" value="${wzrq_esc(parts[1] || '')}" /></div>`;
			} else if (meta.fieldtype === 'Date') {
				value_ctl = `<input type="date" class="form-control wzrq-fv" value="${wzrq_esc(f.value)}" />`;
			} else if (meta.fieldtype === 'Select' && meta.options) {
				value_ctl =
					`<select class="form-control wzrq-fv"><option value="">—</option>` +
					meta.options
						.map((o) => `<option value="${wzrq_esc(o)}"${o === f.value ? ' selected' : ''}>${wzrq_esc(o)}</option>`)
						.join('') +
					`</select>`;
			} else if (meta.fieldtype === 'Float') {
				value_ctl = `<input type="number" class="form-control wzrq-fv" step="1" min="0" value="${wzrq_esc(f.value)}" />`;
			} else {
				value_ctl = `<input type="text" class="form-control wzrq-fv" value="${wzrq_esc(f.value)}" placeholder="${wzrq_esc(meta.placeholder || '')}" />`;
			}
			return `
				<div class="wzrq-filter-row" data-idx="${i}">
					<select class="form-control wzrq-ff">${field_opts}</select>
					<select class="form-control wzrq-fo">${op_opts}</select>
					${value_ctl}
					<button class="btn btn-default btn-sm wzrq-fx" title="${__('Remove filter')}">×</button>
				</div>`;
		}).join(''),
	);
}

function wzrq_op_label(op) {
	const map = {
		'=': '=',
		'!=': '≠',
		like: 'like',
		'not like': 'not like',
		between: 'between',
		'>=': '≥',
		'<=': '≤',
		'>': '>',
		'<': '<',
	};
	return map[op] || op;
}

function wzrq_collect_rows($main) {
	const rows = [];
	$main.find('.wzrq-filter-row').each(function () {
		const $d1 = $(this).find('.wzrq-fd1');
		if ($d1.length) {
			// operator between: dua input tanggal dikumpulkan sebagai array
			rows.push({
				field: $(this).find('.wzrq-ff').val(),
				operator: $(this).find('.wzrq-fo').val(),
				value: [$d1.val() || '', $(this).find('.wzrq-fd2').val() || ''],
			});
			return;
		}
		rows.push({
			field: $(this).find('.wzrq-ff').val(),
			operator: $(this).find('.wzrq-fo').val(),
			value: $(this).find('.wzrq-fv').val() || '',
		});
	});
	WZRQ_FILTERS = rows;
}

function wzrq_update_filter_count($scope) {
	const n = active_filters().length;
	$scope.find('.wzrq-filter-count').text(n ? `(${n})` : '');
	$scope.find('.wzrq-filter-btn').toggleClass('wzrq-filter-active', n > 0);
}

// ---------------- helpers render (global: dipakai on_page_load & on_page_show)

function wzrq_rows($scope) {
	return $scope.data('wzrq_rows') || [];
}

// definisi kolom tabel ala list view ERPNext — urutan tetap, show/hide
// via popover "Choose columns" (persist di localStorage)
const WZRQ_ALL_COLUMNS = [
	{
		key: 'batch',
		label: __('Batch'),
		cls: 'wzrq-col-adonan',
		cell: (r) => `<span class="wzrq-adonan">${r.custom_adonan_ke ? wzrq_esc(r.custom_adonan_ke) : '—'}</span>`,
	},
	{ key: 'item', label: __('Item'), cls: 'wzrq-col-item', cell: (r) => wzrq_esc(r.item_name) },
	{
		key: 'qty',
		label: __('Qty'),
		cls: 'wzrq-col-qty',
		cell: (r) => `${Number(r.produced_qty || 0).toLocaleString('en-US')} <span class="text-muted">${wzrq_esc(r.stock_uom)}</span>`,
	},
	{ key: 'wo', label: __('Work Order'), cls: 'wzrq-col-wo', cell: (r) => wzrq_esc(r.name) },
	{ key: 'warehouse', label: __('Warehouse'), cls: 'wzrq-col-warehouse', cell: (r) => wzrq_esc(r.fg_warehouse || '') },
	{
		key: 'status',
		label: __('Status'),
		cls: 'wzrq-col-status',
		cell: (r) =>
			r.request_active
				? `<span class="indicator-pill orange">${__('Requested')} · <a href="/app/material-request/${wzrq_esc(r.custom_handover_material_request)}">${wzrq_esc(r.custom_handover_material_request)}</a></span>`
				: `<span class="indicator-pill blue">${wzrq_esc(r.status)}</span>`,
	},
];

function wzrq_visible_columns() {
	if (WZRQ_VISIBLE) {
		return WZRQ_VISIBLE;
	}
	let keys = null;
	try {
		keys = JSON.parse(localStorage.getItem('wzrq_columns') || 'null');
	} catch (e) {
		keys = null;
	}
	if (!Array.isArray(keys) || !keys.length) {
		keys = WZRQ_ALL_COLUMNS.map((c) => c.key);
	}
	WZRQ_VISIBLE = keys.filter((k) => WZRQ_ALL_COLUMNS.some((c) => c.key === k));
	return WZRQ_VISIBLE;
}

function wzrq_set_visible_columns(keys) {
	WZRQ_VISIBLE = keys;
	try {
		localStorage.setItem('wzrq_columns', JSON.stringify(keys));
	} catch (e) {
		/* private mode: abaikan */
	}
}

function wzrq_render($scope, rows) {
	$scope.data('wzrq_rows', rows);
	const $main = $scope.find('.layout-main');
	const cols = wzrq_visible_columns().map((key) => WZRQ_ALL_COLUMNS.find((c) => c.key === key));
	$main.find('.wzrq-table thead tr').html(
		`<th class="wzrq-col-check"><input type="checkbox" class="wzrq-check-all" aria-label="${__('Select all')}" /></th>` +
			cols
				.map((c) => `<th class="${c.cls}">${c.label}</th>`)
				.join('') +
			`<th class="wzrq-col-aksi"><button type="button" class="wzrq-cols-btn" title="${__('Choose columns')}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg></button></th>`,
	);
	$main.find('.wzrq-table tbody').html(rows.map((r) => wzrq_row_html(r, cols)).join(''));
	$main.find('.wzrq-empty').toggle(rows.length === 0);
	$main.find('.wzrq-limit').toggle(rows.length >= 50);
	wzrq_update_bulk($scope, new Set());
}

function wzrq_update_bulk($scope, selected) {
	const rows = wzrq_rows($scope);
	const selectable = rows.filter((r) => !r.request_active);
	const n = selectable.filter((r) => selected.has(r.name)).length;
	const $main = $scope.find('.layout-main');
	$main.find('.wzrq-bulk-count').text(n ? __('{0} selected', [n]) : '');
	$main.find('.wzrq-bulk-request').prop('disabled', !n);
	$main.find('.wzrq-bulk-request').text(n ? __('Create Request ({0})', [n]) : __('Create Request'));
	$main.find('.wzrq-bulk-clear').toggle(n > 0);
	$main
		.find('.wzrq-check-all')
		.prop('checked', selectable.length > 0 && n >= selectable.length)
		.prop('indeterminate', n > 0 && n < selectable.length);
}

function wzrq_esc(value) {
	return frappe.utils.escape_html(value == null ? '' : String(value));
}

function wzrq_row_html(r, cols) {
	const active = r.request_active;
	const mr = r.custom_handover_material_request;
	const aksi = active
		? `<button class="btn btn-xs btn-default wzrq-cancel" data-mr="${wzrq_esc(mr)}">${__('Cancel')}</button>`
		: '';
	return `
		<tr class="wzrq-row${active ? ' is-active' : ''}" data-wo="${wzrq_esc(r.name)}">
			<td class="wzrq-col-check"><input type="checkbox" class="wzrq-check"${active ? ' disabled' : ''} aria-label="${wzrq_esc(r.name)}" /></td>
			${cols.map((c) => `<td class="${c.cls}">${c.cell(r)}</td>`).join('')}
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
					<div class="wzrq-dt-title">${__('Batch')} <b>${wzrq_esc(r.custom_adonan_ke || '-')}</b> · ${wzrq_esc(r.item_name)}</div>
					<div class="wzrq-dt-meta text-muted">${wzrq_esc(r.name)} · ${Number(r.produced_qty || 0).toLocaleString('en-US')} ${wzrq_esc(r.stock_uom)}</div>
				</td>
				<td class="wzrq-dt-cell"><input type="number" class="form-control wzrq-kg1" min="0" step="0.01" placeholder="kg" title="${__('Box 1 — kg')}" /></td>
				<td class="wzrq-dt-cell"><input type="number" class="form-control wzrq-qty1" min="0" step="1" value="${Number(r.produced_qty || 0)}" title="${__('Box 1 — qty')}" /></td>
				<td class="wzrq-dt-cell2">
					<button type="button" class="btn btn-link wzrq-addbox2">+ ${__('Box 2')}</button>
					<div class="wzrq-box2-inputs" style="display:none">
						<input type="number" class="form-control wzrq-kg2" min="0" step="0.01" placeholder="kg" title="${__('Box 2 — kg')}" />
						<input type="number" class="form-control wzrq-qty2" min="0" step="1" value="0" title="${__('Box 2 — qty')}" />
					</div>
				</td>
			</tr>`
		)
		.join('');

	const d = new frappe.ui.Dialog({
		title: __('Box Allocation — {0} Work Orders', [wos.length]),
		size: 'large',
	});
	d.$body.html(`
		<p class="text-muted wzrq-dt-hint">${__('Box 1 is required. Box 2 is optional — click + Box 2 to add it.')}</p>
		<table class="wzrq-dtable">
			<thead>
				<tr>
					<th class="wzrq-dt-wo">${__('Work Order')}</th>
					<th>${__('Box 1 · kg')}</th>
					<th>${__('Box 1 · qty')}</th>
					<th>${__('Box 2 · optional')}</th>
				</tr>
			</thead>
			<tbody>${rows_html}</tbody>
		</table>
	`);

	// Box 2 opsional: munculkan pasangan input kg/qty saat diminta
	d.$body.on('click', '.wzrq-addbox2', function () {
		const $cell = $(this).closest('.wzrq-dt-cell2');
		$(this).hide();
		$cell.find('.wzrq-box2-inputs').show().find('.wzrq-kg2').trigger('focus');
	});

	d.set_primary_action(__('Create Request'), () => submit_bulk(d, done));
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
		if (kg1 === '' || kg1 === null || q1 === '' || q1 === null) {
			invalid = $tr.attr('data-wo');
			return;
		}
		// Box 2 hanya dikirim bila pasangan inputnya dimunculkan
		let box_2 = 0;
		let box_2_qty = 0;
		if ($tr.find('.wzrq-box2-inputs').is(':visible')) {
			const kg2 = $tr.find('.wzrq-kg2').val();
			box_2 = kg2 === '' || kg2 === null ? 0 : parseFloat(kg2);
			box_2_qty = parseInt($tr.find('.wzrq-qty2').val() || '0', 10) || 0;
		}
		payloads.push({
			work_order: $tr.attr('data-wo'),
			box_1: parseFloat(kg1),
			box_1_qty: parseInt(q1, 10),
			box_2,
			box_2_qty,
		});
	});
	if (invalid) {
		frappe.msgprint({
			title: __('Incomplete data'),
			indicator: 'red',
			message: __('Fill in Box 1 (kg and qty) for every row — check {0}.', [invalid]),
		});
		return;
	}

	frappe.freeze(__('Creating handover requests...'));
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
			title: ok_list.length ? __('Partially created') : __('All failed'),
			indicator: ok_list.length ? 'orange' : 'red',
			message:
				(ok_list.length
					? `<p>${__('Created: {0}', [wzrq_esc(ok_list.join(', '))])}</p>`
					: '') +
				`<p><b>${__('Failed')}:</b></p><ul>` +
				fail_list
					.map((f) => `<li><b>${wzrq_esc(f.wo)}</b> — ${wzrq_esc(f.error)}</li>`)
					.join('') +
				'</ul>',
		});
	} else {
		frappe.show_alert({
			message: __('{0} requests created', [ok_list.length]),
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
	frappe.confirm(__('Cancel handover request {0} that has not been shipped?', [material_request]), () => {
		frappe.call({
			method: 'production_app.api.handover.cancel_request',
			args: { material_request: material_request },
			freeze: true,
			freeze_message: __('Cancelling request...'),
		}).then(() => {
			frappe.show_alert({ message: __('Request cancelled'), indicator: 'orange' });
			done && done();
		});
	});
}
