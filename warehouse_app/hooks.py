app_name = "warehouse_app"
app_title = "Warehouse App"
app_publisher = "Muhammad Yusuf Tri Daryanto"
app_description = "Gudang (warehouse) operations, separate from production_app"
app_email = "ropierpnext@gmail.com"
app_license = "mit"

# Installation
# ------------------
after_install = "warehouse_app.upgrade.apply"
after_migrate = ["warehouse_app.upgrade.apply"]

# Fixtures
# ------------------
# Role gudang dibawa app (site baru mis. Frappe Cloud tidak memilikinya;
# workspace + Page kita role-scoped ke role ini).
fixtures = [
	{
		"dt": "Role",
		"filters": [["name", "in", ["Gudang Barang Jadi"]]],
	},
]


# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "warehouse_app",
		"logo": "/assets/warehouse_app/logo.svg",
		"title": "Warehouse App",
		"route": "/app/gudang",
	},
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/warehouse_app/css/warehouse_app.css"
# app_include_js = "/assets/warehouse_app/js/warehouse_app.js"

# include js, css files in header of web template
# web_include_css = "/assets/warehouse_app/css/warehouse_app.css"
# web_include_js = "/assets/warehouse_app/js/warehouse_app.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "warehouse_app/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# Doctype Overrides
# ------------------
override_doctype_class = {
	"Purchase Receipt": "warehouse_app.overrides.purchase_receipt.WarehousePurchaseReceipt",
	"Batch": "warehouse_app.overrides.batch.WarehouseBatch",
}

# include js in doctype views
doctype_js = {
	"Batch": "public/js/batch.js",
	"Purchase Receipt": "public/js/purchase_receipt.js",
	"Stock Entry": "public/js/stock_entry.js",
	"Delivery Note": "public/js/delivery_note.js",
	"Sales Invoice": "public/js/sales_invoice.js",
	"Purchase Invoice": "public/js/purchase_invoice.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "warehouse_app/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "warehouse_app.utils.jinja_methods",
# 	"filters": "warehouse_app.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "warehouse_app.install.before_install"
# after_install = "warehouse_app.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "warehouse_app.uninstall.before_uninstall"
# after_uninstall = "warehouse_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "warehouse_app.utils.before_app_install"
# after_app_install = "warehouse_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "warehouse_app.utils.before_app_uninstall"
# after_app_uninstall = "warehouse_app.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "warehouse_app.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "warehouse_app.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["warehouse_app.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Stock Entry": {
		"validate": "warehouse_app.overrides.batch_uom.apply_batch_uom_conversion",
		"on_submit": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
		"on_cancel": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
	},
	"Purchase Receipt": {
		"validate": "warehouse_app.overrides.batch_uom.apply_batch_uom_conversion",
		"on_submit": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
		"on_cancel": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
	},
	"Delivery Note": {
		"validate": "warehouse_app.overrides.batch_uom.apply_batch_uom_conversion",
		"on_submit": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
		"on_cancel": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
	},
	"Sales Invoice": {
		"validate": "warehouse_app.overrides.batch_uom.apply_batch_uom_conversion",
		"on_submit": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
		"on_cancel": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
	},
	"Purchase Invoice": {
		"validate": "warehouse_app.overrides.batch_uom.apply_batch_uom_conversion",
		"on_submit": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
		"on_cancel": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
	},
	"Subcontracting Receipt": {
		"validate": "warehouse_app.overrides.batch_uom.apply_batch_uom_conversion",
		"on_submit": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
		"on_cancel": "warehouse_app.overrides.batch_uom.sync_batch_qty_after_transaction",
	},
	"Material Request": {
		"validate": "warehouse_app.overrides.batch_uom.apply_batch_uom_conversion",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"warehouse_app.tasks.all"
# 	],
# 	"daily": [
# 		"warehouse_app.tasks.daily"
# 	],
# 	"hourly": [
# 		"warehouse_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"warehouse_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"warehouse_app.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "warehouse_app.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "warehouse_app.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------

override_whitelisted_methods = {
	"erpnext.controllers.queries.get_batch_no": "warehouse_app.overrides.batch_uom.warehouse_get_batch_no",
	"erpnext.stock.doctype.batch.batch.get_batch_qty": "warehouse_app.overrides.batch_uom.warehouse_get_batch_qty",
	"erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle.add_serial_batch_ledgers": "warehouse_app.overrides.batch_uom.warehouse_add_serial_batch_ledgers",
	"erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle.get_serial_batch_ledgers": "warehouse_app.overrides.batch_uom.warehouse_get_serial_batch_ledgers",
	"erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle.get_auto_data": "warehouse_app.overrides.batch_uom.warehouse_get_auto_data",
}

# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "warehouse_app.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["warehouse_app.utils.before_request"]
# after_request = ["warehouse_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["warehouse_app.utils.before_job"]
# after_job = ["warehouse_app.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"warehouse_app.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

