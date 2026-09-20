// W11: halaman Settings gudang serah terima. Form tipis dua field
// (Source/Target warehouse) di atas setting Manufacturing Settings
// milik production_app — lihat gudang_settings.py untuk batasnya.

frappe.pages['gudang_settings'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Settings'),
		single_column: true,
	});

	const $main = $(wrapper).find('.layout-main');
	// .layout-main Desk v16 = flex row: satu root full-width dengan padding
	$main.html(`
		<div class="wgs-root">
			<p class="text-muted wgs-desc">
				${__('Warehouses used when the warehouse team creates handover requests.')}
			</p>
			<div class="wgs-form">
				<div class="wgs-field">
					<label class="wgs-label">${__('Source Warehouse')}</label>
					<select class="form-control wgs-input" id="wgs-source"></select>
					<p class="wgs-help text-muted">${__('Where the goods come from. Leave empty to follow the production lot warehouse automatically.')}</p>
				</div>
				<div class="wgs-field">
					<label class="wgs-label">${__('Target Warehouse')} <span class="text-danger">*</span></label>
					<select class="form-control wgs-input" id="wgs-target"></select>
					<p class="wgs-help text-muted">${__('Where handover requests deliver the goods. Required to create a request.')}</p>
				</div>
				<div class="wgs-actions">
					<button class="btn btn-primary wgs-save">${__('Save')}</button>
				</div>
			</div>
		</div>
	`);

	const $source = $main.find('#wgs-source');
	const $target = $main.find('#wgs-target');
	const $save = $main.find('.wgs-save');
	let warehouses = [];

	function fill_select($el, value) {
		$el.html(
			`<option value="">—</option>` +
				warehouses
					.map(
						(w) =>
							`<option value="${frappe.utils.escape_html(w)}"${w === value ? ' selected' : ''}>${frappe.utils.escape_html(w)}</option>`,
					)
					.join(''),
		);
	}

	async function load_settings() {
		const [opts, settings] = await Promise.all([
			frappe.call({ method: 'warehouse_app.warehouse_app.gudang_settings.warehouse_options' }),
			frappe.call({ method: 'warehouse_app.warehouse_app.gudang_settings.get_handover_settings' }),
		]);
		warehouses = opts.message || [];
		fill_select($source, settings.message.source);
		fill_select($target, settings.message.target);
	}

	$save.on('click', async () => {
		$save.prop('disabled', true);
		try {
			const r = await frappe.call({
				method: 'warehouse_app.warehouse_app.gudang_settings.set_handover_warehouses',
				args: { source: $source.val() || '', target: $target.val() || '' },
			});
			fill_select($source, r.message.source);
			fill_select($target, r.message.target);
			frappe.show_alert({ message: __('Settings saved'), indicator: 'green' });
		} catch (e) {
			// error server (role/validasi) sudah tampil sebagai toast frappe
		} finally {
			$save.prop('disabled', false);
		}
	});

	load_settings();
};
