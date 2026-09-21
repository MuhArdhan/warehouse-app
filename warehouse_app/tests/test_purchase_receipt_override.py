import frappe
from warehouse_app.overrides.purchase_receipt import (
	WarehousePurchaseReceipt,
	get_purchase_receipt_label_data,
	render_labels_html,
	_format_short_date,
	_get_qr_svg_base64
)


def run_tests():
	print("--- Running Warehouse App Purchase Receipt Override Tests ---")

	# Test 1: Date formatting
	assert _format_short_date("2026-06-30") == "30-06-26", f"Expected 30-06-26 but got {_format_short_date('2026-06-30')}"
	assert _format_short_date("2026-10-28") == "28-10-26", f"Expected 28-10-26 but got {_format_short_date('2026-10-28')}"
	print("[PASS] Test 1: Date formatting passed")

	# Test 2: QR SVG generation
	svg = _get_qr_svg_base64("PJ260004")
	assert "<svg" in svg and "</svg>" in svg, "QR SVG must contain <svg> tags"
	print("[PASS] Test 2: QR Code SVG generation passed")

	# Test 3: DocType class override
	doc_class = frappe.new_doc("Purchase Receipt")
	assert isinstance(doc_class, WarehousePurchaseReceipt), f"Expected WarehousePurchaseReceipt instance, got {type(doc_class)}"
	print(f"[PASS] Test 3: DocType override active -> {type(doc_class).__name__}")

	# Test 4: get_purchase_receipt_label_data
	prs = frappe.get_all("Purchase Receipt", limit=1)
	if prs:
		pr_name = prs[0].name
		data = get_purchase_receipt_label_data(pr_name)
		assert "items" in data
		assert "receipt_date" in data
		assert "receipt_date_short" in data
		print(f"[PASS] Test 4: Label data fetched for {pr_name} ({len(data['items'])} items)")

	# Test 5: Render label HTML matching specification
	sample_items = [
		{
			"item_code": "PJ260004",
			"item_name": "Dough Gempi",
			"receipt_date": "2026-06-30",
			"expiry_date": "2026-10-28",
			"qty": 1
		}
	]
	html = render_labels_html(sample_items)
	assert "PJ260004" in html
	assert "Dough Gempi" in html
	assert "RCP : 30-06-26" in html
	assert "EXP : 28-10-26" in html
	assert "<svg" in html
	print("[PASS] Test 5: Render HTML output verified with exact layout and fields")

	# Test 6: Quantity multiplication (printing multiple labels)
	multi_items = [
		{
			"item_code": "PJ260004",
			"item_name": "Dough Gempi",
			"receipt_date": "2026-06-30",
			"expiry_date": "2026-10-28",
			"qty": 3
		}
	]
	html_multi = render_labels_html(multi_items)
	assert html_multi.count("class=\"label-page\"") == 3, f"Expected 3 label pages, got {html_multi.count('class=\"label-page\"')}"
	print("[PASS] Test 6: Quantity multiplication verified (3 labels generated for qty=3)")

	# Test 7: Missing expiry_date raises error
	try:
		render_labels_html([{"item_code": "PJ260004", "item_name": "Dough Gempi", "expiry_date": ""}])
		assert False, "Expected ValidationError when expiry_date is missing"
	except frappe.ValidationError:
		print("[PASS] Test 7: Validation error properly raised when expiry_date is missing")

	# Test 8: Total quantity exceeding actual_qty raises error
	try:
		render_labels_html([{"item_code": "PJ260004", "item_name": "Dough Gempi", "expiry_date": "2026-10-28", "qty": 5, "actual_qty": 3}])
		assert False, "Expected ValidationError when qty exceeds actual_qty"
	except frappe.ValidationError:
		print("[PASS] Test 8: Validation error properly raised when qty exceeds actual_qty")

	print("\nALL 8 TESTS PASSED SUCCESSFULLY!")
	return True
