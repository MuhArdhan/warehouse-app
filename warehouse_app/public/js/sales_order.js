// warehouse_app owns this replacement for the native Sales Order Pick List action.
frappe.provide("warehouse_app.sales_order");

warehouse_app.sales_order.create_pick_lists = function (frm) {
	if (frm.doc.__unsaved) {
		frappe.throw(__("You have unsaved changes in this form. Please save before you continue."));
	}

	return frappe.call({
		method: "warehouse_app.overrides.sales_order.create_pick_lists",
		args: { source_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Creating Pick Lists..."),
		callback: function (response) {
			if (response.exc) {
				return;
			}

			const result = response.message || {};
			if (result.pick_list) {
				const pick_list = result.pick_list;
				frappe.model.sync(pick_list);
				frappe.set_route("Form", pick_list.doctype, pick_list.name);
				return;
			}

			const pick_lists = result.draft_pick_lists || [];
			const links = pick_lists
				.map((pick_list) => {
					const label = `${__("ID Pick List")} (${__(pick_list.category)}): ${pick_list.name}`;
					return frappe.utils.get_form_link("Pick List", pick_list.name, true, label);
				})
				.join("<br>");

			frappe.msgprint({
				title: __("Berhasil Membuat Draft Pick List"),
				indicator: "green",
				message: links,
			});
		},
	});
};

// The native button calls this controller method directly. Replacing its
// prototype keeps the standard button and changes only its implementation.
erpnext.selling.SalesOrderController.prototype.create_pick_list = function () {
	return warehouse_app.sales_order.create_pick_lists(this.frm);
};
