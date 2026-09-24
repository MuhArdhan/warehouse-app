import io
import json
import frappe
from frappe.utils import formatdate, getdate
import pyqrcode
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt


class WarehousePurchaseReceipt(PurchaseReceipt):
	"""
	Override of ERPNext's Purchase Receipt for warehouse_app.
	Keeps native functionality 100% intact while providing custom hooks and methods.
	"""
	pass


def _format_short_date(date_val):
	"""
	Format date as DD-MM-YY (e.g. 30-06-26) to match the thermal label design.
	"""
	if not date_val:
		return ""
	try:
		d = getdate(date_val)
		return d.strftime("%d-%m-%y")
	except Exception:
		return str(date_val)


def _get_qr_svg_base64(content):
	"""
	Generate SVG for content using pyqrcode and return as base64 data URI or SVG string.
	"""
	if not content:
		return ""
	qr = pyqrcode.create(content)
	buf = io.BytesIO()
	qr.svg(buf, scale=3, quiet_zone=0)
	raw_svg = buf.getvalue().decode("utf-8")
	# Strip xml declaration if embedded directly
	if "<?xml" in raw_svg:
		raw_svg = raw_svg.split("?>", 1)[-1].strip()
	return raw_svg


@frappe.whitelist()
def get_purchase_receipt_label_data(purchase_receipt_name):
	"""
	Retrieve items and receipt date from Purchase Receipt for label printing modal.
	"""
	pr = frappe.get_doc("Purchase Receipt", purchase_receipt_name)
	pr.check_permission("read")

	receipt_date_raw = str(pr.posting_date) if pr.posting_date else ""
	receipt_date_short = _format_short_date(pr.posting_date)

	items_data = []
	for item in pr.items:
		exp_raw = ""
		# Try to look up batch expiry date if batch is set
		batch_no = item.batch_no
		if not batch_no and item.serial_and_batch_bundle:
			# Fetch from bundle
			entries = frappe.get_all(
				"Serial and Batch Entry",
				filters={"parent": item.serial_and_batch_bundle},
				fields=["batch_no"],
				limit=1,
			)
			if entries and entries[0].batch_no:
				batch_no = entries[0].batch_no

		if batch_no:
			batch_doc = frappe.db.get_value(
				"Batch",
				batch_no,
				["expiry_date", "manufacturing_date"],
				as_dict=True,
			)
			if batch_doc and batch_doc.expiry_date:
				exp_raw = str(batch_doc.expiry_date)

		qty = 1
		if item.qty:
			try:
				qty = max(1, int(round(float(item.qty))))
			except Exception:
				qty = 1

		items_data.append(
			{
				"name": item.name,
				"item_code": item.item_code or "",
				"item_name": item.item_name or "",
				"receipt_date": receipt_date_raw,
				"receipt_date_short": receipt_date_short,
				"expiry_date": exp_raw,
				"expiry_date_short": _format_short_date(exp_raw),
				"qty": qty,
				"actual_qty": qty,
			}
		)

	return {
		"purchase_receipt": pr.name,
		"receipt_date": receipt_date_raw,
		"receipt_date_short": receipt_date_short,
		"items": items_data,
	}


@frappe.whitelist()
def render_labels_html(items_json=None):
	"""
	Render complete thermal label HTML matching the user's label image specification:
	- Left: QR Code (encoding SKU) + SKU text below it.
	- Right: Item Name (bold), SKU, RCP (Receipt Date DD-MM-YY), EXP (DD-MM-YY).
	"""
	if items_json is None:
		items_json = frappe.form_dict.get("items_json") or frappe.form_dict.get("items") or []

	if isinstance(items_json, str):
		try:
			items = json.loads(items_json)
		except Exception:
			items = []
	elif isinstance(items_json, dict):
		items = items_json.get("items_json") or items_json.get("items") or [items_json]
	else:
		items = items_json or []

	if isinstance(items, str):
		try:
			items = json.loads(items)
		except Exception:
			items = []

	# Validate total label quantity against actual_qty
	item_totals = {}
	for it in items:
		key = it.get("item_key") or it.get("item_code")
		actual = it.get("actual_qty")
		actual_int = None
		if actual is not None and str(actual).strip() != "":
			try:
				actual_int = int(actual)
			except (ValueError, TypeError):
				actual_int = None

		if key not in item_totals:
			item_totals[key] = {
				"item_code": it.get("item_code") or "",
				"actual_qty": actual_int,
				"total_qty": 0,
			}
		try:
			q = max(1, int(it.get("qty") or 1))
		except Exception:
			q = 1
		item_totals[key]["total_qty"] += q

	for key, info in item_totals.items():
		if info["actual_qty"] is not None and info["total_qty"] > info["actual_qty"]:
			frappe.throw(
				frappe._("Total quantity label untuk item {0} ({1}) melebihi aktual quantity ({2}).").format(
					info["item_code"], info["total_qty"], info["actual_qty"]
				)
			)

	labels = []
	for it in items:
		sku = (it.get("item_code") or "").strip()
		name = (it.get("item_name") or "").strip()
		rcp = _format_short_date(it.get("receipt_date"))
		exp_raw = (it.get("expiry_date") or "").strip()
		if not exp_raw:
			frappe.throw(frappe._("Tanggal EXP (Expiry Date) wajib diisi untuk item {0}.").format(sku or name))
		exp = _format_short_date(exp_raw)
		try:
			qty = max(1, int(it.get("qty") or 1))
		except Exception:
			qty = 1
		qr_svg = _get_qr_svg_base64(sku)

		for _ in range(qty):
			labels.append(
				{
					"sku": sku,
					"item_name": name,
					"rcp": rcp,
					"exp": exp,
					"qr_svg": qr_svg,
				}
			)

	html_content = """<!DOCTYPE html>
<html>
<head>
	<meta charset="utf-8">
	<title>Print Labels</title>
	<style>
		@page {
			size: 100mm 30mm;
			margin: 0;
		}
		* {
			box-sizing: border-box;
			-webkit-print-color-adjust: exact;
			print-color-adjust: exact;
		}
		body {
			margin: 0;
			padding: 0;
			font-family: Arial, Helvetica, sans-serif;
			background: #fff;
			color: #000;
		}
		.label-row {
			width: 100mm;
			height: 30mm;
			display: flex;
			flex-direction: row;
			page-break-after: always;
			break-after: page;
			overflow: hidden;
		}
		.label-page {
			flex: 0 0 50mm;
			width: 50mm;
			height: 30mm;
			padding: 2.2mm 2.5mm 1.5mm 2.5mm;
			display: flex;
			flex-direction: row;
			align-items: center;
			justify-content: space-between;
			overflow: hidden;
		}
		.label-left {
			width: 38%;
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			text-align: center;
		}
		.label-left .qr-wrapper {
			width: 16.5mm;
			height: 16.5mm;
			display: flex;
			align-items: center;
			justify-content: center;
		}
		.label-left .qr-wrapper svg {
			width: 100%;
			height: 100%;
			display: block;
		}
		.label-left .sku-text {
			font-size: 7.5pt;
			font-weight: 800;
			margin-top: 1.2mm;
			letter-spacing: 0.1px;
			line-height: 1.1;
			word-break: break-all;
		}
		.label-right {
			width: 60%;
			padding-left: 2mm;
			display: flex;
			flex-direction: column;
			justify-content: center;
		}
		.label-right .item-name {
			font-size: 9.5pt;
			font-weight: 800;
			line-height: 1.15;
			margin-bottom: 2mm;
			word-break: break-word;
			text-transform: capitalize;
		}
		.label-right .meta-line {
			font-size: 7.5pt;
			font-weight: 800;
			line-height: 1.35;
			white-space: nowrap;
			letter-spacing: 0.2px;
		}
		@media screen {
			body {
				background: #eceff1;
				padding: 76px 20px 20px;
				display: flex;
				flex-direction: column;
				align-items: center;
				gap: 15px;
			}
			.screen-toolbar {
				position: fixed;
				top: 0;
				left: 0;
				right: 0;
				height: 56px;
				z-index: 1000;
				display: flex;
				align-items: center;
				justify-content: space-between;
				padding: 0 20px;
				background: #fff;
				border-bottom: 1px solid #d8dde3;
				box-shadow: 0 1px 4px rgba(0,0,0,0.08);
			}
			.total-labels {
				font-size: 14px;
				font-weight: 700;
				color: #202124;
			}
			.print-button {
				display: inline-flex;
				align-items: center;
				gap: 8px;
				border: 0;
				border-radius: 6px;
				padding: 9px 16px;
				background: #2490ef;
				color: #fff;
				font-size: 13px;
				font-weight: 600;
				cursor: pointer;
			}
			.print-button svg { width: 16px; height: 16px; }
			.print-button:hover { background: #1678d3; }
			.label-row {
				background: #fff;
				box-shadow: 0 2px 6px rgba(0,0,0,0.15);
				border-radius: 4px;
			}
		}
		@media print {
			.screen-toolbar { display: none !important; }
		}
	</style>
</head>
<body>
"""
	total_labels = len(labels)
	total_labels_text = frappe._("Total Labels: {0}").format(total_labels)
	print_text = frappe._("Print")
	html_content += f"""
	<div class="screen-toolbar">
		<div class="total-labels">{total_labels_text}</div>
		<button class="print-button" type="button" onclick="window.print()">
			<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
				<path d="M7 8V3h10v5M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2M7 14h10v7H7v-7Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
				<path d="M17 11h.01" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
			</svg>
			<span>{print_text}</span>
		</button>
	</div>
"""

	for row_start in range(0, len(labels), 2):
		html_content += '<div class="label-row">'
		for lbl in labels[row_start : row_start + 2]:
			html_content += f"""
	<div class="label-page">
		<div class="label-left">
			<div class="qr-wrapper">
				{lbl['qr_svg']}
			</div>
			<div class="sku-text">{frappe.utils.escape_html(lbl['sku'])}</div>
		</div>
		<div class="label-right">
			<div class="item-name">{frappe.utils.escape_html(lbl['item_name'])}</div>
			<div class="meta-line">SKU : {frappe.utils.escape_html(lbl['sku'])}</div>
			<div class="meta-line">RCP : {frappe.utils.escape_html(lbl['rcp'])}</div>
			<div class="meta-line">EXP : {frappe.utils.escape_html(lbl['exp'])}</div>
		</div>
	</div>
"""
		html_content += '</div>'

	html_content += """
	<script>
		window.onload = function() {
			window.print();
		};
	</script>
</body>
</html>
"""
	return html_content
