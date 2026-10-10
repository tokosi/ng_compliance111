"""VAT and WHT setup for a company on the FEDCO chart (run setup.coa.import_chart first).

    bench --site <site> execute ng_compliance.setup.accounts.setup_nigeria_accounts \
        --kwargs "{'company': 'FEDCO West Africa Limited'}"

Follows the NRS VAT rules (nrs.gov.ng/tax-information/value-added-tax, Jan 2026):
  * standard rate 7.5% (output VAT -> 20013 Statutory Payables - VAT/Levies)
  * exported goods and services are zero-rated (0%), input VAT on them stays recoverable
    (-> 10022 Export VAT Recoverable)
  * exempt supplies (basic food, medical, educational...) carry no VAT, and input VAT on
    exempt supplies can't be claimed
  * input VAT on capital expenditure and services is fully recoverable
  * non-resident suppliers without Nigerian VAT on the invoice: the Nigerian buyer self-charges
    and remits the VAT (reverse charge)
  * monthly return (VAT 002) by the 21st of the following month -> report "Nigeria VAT Return"

Creates (idempotently) Tax Categories, Sales/Purchase Taxes and Charges Templates, Item Tax
Templates, Tax Rules that pick the right template from the party's Tax Category, and the
Deduction of Tax at Source (Withholding) Regulations 2024 WHT categories.
"""

import frappe

from ng_compliance.setup.profile import account

VAT_RATE = 7.5

TAX_CATEGORIES = ["NG Domestic", "NG Export", "NG Exempt", "NG Non-resident Supplier", "NG Import"]

SALES_TEMPLATES = [
	# title, rate, tax category, default?
	("NG VAT 7.5%", VAT_RATE, "NG Domestic", 1),
	("NG VAT Zero-Rated Export", 0, "NG Export", 0),
	("NG VAT Exempt", 0, "NG Exempt", 0),
]

# Resident recipient rates; double the rate where the supplier has no TIN. Confirm with your adviser.
WHT_CATEGORIES = [
	("WHT - Professional/Consultancy/Mgmt/Technical 5%", 5),
	("WHT - Commission/Brokerage 5%", 5),
	("WHT - Supply of Goods 2%", 2),
	("WHT - Other Services 2%", 2),
	("WHT - Rent/Hire/Lease 10%", 10),
	("WHT - Interest/Dividend/Royalty 10%", 10),
	("WHT - Directors Fees (Individual) 15%", 15),
	("WHT - Non-resident Professional 10%", 10),
]


def _abbr(company):
	return frappe.get_cached_value("Company", company, "abbr")


@frappe.whitelist()
def setup_nigeria_accounts(company, wht=1):
	frappe.only_for(("System Manager", "Accounts Manager"))
	vat_out = account(company, "vat_output")
	vat_in_local = account(company, "vat_input_local")
	vat_in_import = account(company, "vat_input_import")
	missing = [k for k, v in (("vat_output", vat_out), ("vat_input_local", vat_in_local),
		("vat_input_import", vat_in_import)) if not v]
	if missing:
		frappe.throw(f"Accounts {missing} not found - run ng_compliance.setup.coa.import_chart first")

	log = create_tax_categories()
	for title, rate, cat, default in SALES_TEMPLATES:
		log.append(_template("Sales Taxes and Charges Template", title, company, cat, default,
			[_row(vat_out, rate, f"VAT @ {rate:g}%" if rate else f"{title.replace('NG VAT ', '')} supply (VAT 0%)")]))

	log.append(_template("Purchase Taxes and Charges Template", "NG Input VAT 7.5% (Local)", company,
		"NG Domestic", 1, [_row(vat_in_local, VAT_RATE, "Input VAT @ 7.5%", add_deduct="Add")]))
	log.append(_template("Purchase Taxes and Charges Template", "NG Import VAT 7.5% (Customs)", company,
		"NG Import", 0, [_row(vat_in_import, VAT_RATE, "Import VAT @ 7.5% paid at Customs", add_deduct="Add")]))
	log.append(_template("Purchase Taxes and Charges Template", "NG VAT Reverse Charge (Non-resident)", company,
		"NG Non-resident Supplier", 0, [
			_row(vat_in_local, VAT_RATE, "Self-charged input VAT @ 7.5%", add_deduct="Add"),
			_row(vat_out, VAT_RATE, "VAT withheld for remittance to NRS @ 7.5%", add_deduct="Deduct"),
		]))

	log += create_item_tax_templates(company, vat_out, vat_in_local)
	log += create_tax_rules(company)
	if int(wht):
		log += create_wht_categories(company)
	frappe.db.commit()
	for line in log:
		print(line)
	return log


def _row(account_head, rate, description, add_deduct=None):
	row = {"charge_type": "On Net Total", "account_head": account_head, "description": description, "rate": rate}
	if add_deduct:
		row.update({"category": "Total", "add_deduct_tax": add_deduct})
	return row


def create_tax_categories():
	log = []
	for title in TAX_CATEGORIES:
		if not frappe.db.exists("Tax Category", title):
			frappe.get_doc({"doctype": "Tax Category", "title": title}).insert(ignore_permissions=True)
			log.append(f"Tax Category {title}: created")
	return log


def _template(doctype, title, company, tax_category, is_default, rows):
	name = f"{title} - {_abbr(company)}"
	if frappe.db.exists(doctype, name):
		return f"{doctype} {name}: exists"
	t = frappe.new_doc(doctype)
	t.title = title
	t.company = company
	t.tax_category = tax_category
	t.is_default = is_default
	for r in rows:
		t.append("taxes", r)
	t.insert(ignore_permissions=True)
	return f"{doctype} {t.name}: created"


def create_item_tax_templates(company, vat_out, vat_in):
	"""Item-level overrides inside a 7.5% invoice: exempt items, zero-rated items."""
	log = []
	for title in ("NG VAT Exempt", "NG VAT Zero Rated"):
		name = f"{title} - {_abbr(company)}"
		if frappe.db.exists("Item Tax Template", name):
			log.append(f"Item Tax Template {name}: exists")
			continue
		t = frappe.new_doc("Item Tax Template")
		t.title = title
		t.company = company
		t.append("taxes", {"tax_type": vat_out, "tax_rate": 0})
		t.append("taxes", {"tax_type": vat_in, "tax_rate": 0})
		t.insert(ignore_permissions=True)
		log.append(f"Item Tax Template {t.name}: created")
	return log


def create_tax_rules(company):
	"""Party Tax Category -> template, so invoices pick the right VAT treatment automatically."""
	abbr = _abbr(company)
	rules = [
		("Sales", "NG Domestic", "sales_tax_template", f"NG VAT 7.5% - {abbr}"),
		("Sales", "NG Export", "sales_tax_template", f"NG VAT Zero-Rated Export - {abbr}"),
		("Sales", "NG Exempt", "sales_tax_template", f"NG VAT Exempt - {abbr}"),
		("Purchase", "NG Domestic", "purchase_tax_template", f"NG Input VAT 7.5% (Local) - {abbr}"),
		("Purchase", "NG Import", "purchase_tax_template", f"NG Import VAT 7.5% (Customs) - {abbr}"),
		("Purchase", "NG Non-resident Supplier", "purchase_tax_template", f"NG VAT Reverse Charge (Non-resident) - {abbr}"),
	]
	log = []
	for tax_type, cat, field, template in rules:
		if not frappe.db.exists(
			"Purchase Taxes and Charges Template" if tax_type == "Purchase" else "Sales Taxes and Charges Template",
			template,
		):
			continue
		if frappe.db.exists("Tax Rule", {"company": company, "tax_type": tax_type, "tax_category": cat}):
			continue
		try:
			frappe.get_doc({
				"doctype": "Tax Rule",
				"tax_type": tax_type,
				"tax_category": cat,
				field: template,
				"company": company,
				"priority": 1,
			}).insert(ignore_permissions=True)
			log.append(f"Tax Rule {tax_type} / {cat} -> {template}: created")
		except Exception as e:
			frappe.db.rollback()
			log.append(f"! Tax Rule {tax_type} / {cat}: {e}")
	return log


def _ensure_wht_group(name="Nigeria WHT (Resident)"):
	"""v16 requires a Tax Withholding Group on each rate row."""
	if not frappe.db.exists("DocType", "Tax Withholding Group"):
		return None
	if frappe.db.exists("Tax Withholding Group", name):
		return name
	g = frappe.new_doc("Tax Withholding Group")
	g.group_name = name
	g.insert(ignore_permissions=True)
	return g.name


def create_wht_categories(company):
	log = []
	wht_acc = account(company, "wht_payable")
	if not wht_acc:
		return ["Tax Withholding Categories: SKIPPED, WHT payable account (20012) missing"]
	meta = frappe.get_meta("Tax Withholding Category")
	group = _ensure_wht_group()
	for title, rate in WHT_CATEGORIES:
		if frappe.db.exists("Tax Withholding Category", title):
			doc = frappe.get_doc("Tax Withholding Category", title)
			if not any(r.company == company for r in doc.get("accounts") or []):
				doc.append("accounts", {"company": company, "account": wht_acc})
				doc.save(ignore_permissions=True)
			log.append(f"Tax Withholding Category {title}: exists")
			continue
		try:
			doc = frappe.new_doc("Tax Withholding Category")
			doc.name = title
			doc.set("__newname", title)
			doc.flags.name_set = True
			if meta.has_field("category_name"):
				doc.category_name = title
			doc.append("rates", {
				"from_date": "2025-01-01",
				"to_date": "2099-12-31",
				"tax_withholding_rate": rate,
				"single_threshold": 0,
				"cumulative_threshold": 0,
				"tax_withholding_group": group,
			})
			doc.append("accounts", {"company": company, "account": wht_acc})
			doc.insert(ignore_permissions=True)
			log.append(f"Tax Withholding Category {title}: created")
		except Exception as e:
			frappe.db.rollback()
			log.append(f"Tax Withholding Category {title}: FAILED ({e}); create it manually")
	return log
