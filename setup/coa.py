"""Load the FEDCO chart of accounts (data/fedco_coa.json) into a company.

Two routes:

A. New company, no transactions yet -> ERPNext's own tool replaces the chart completely:
   Accounting > Chart of Accounts Importer > company > attach data/fedco_coa_importer.csv > Import.
   Then run `set_company_defaults` below.

B. Existing company (already has the Standard chart and/or transactions) -> this script ADDS the
   FEDCO headline groups (H01..H24) and sub-ledgers under the existing root groups, matching on
   account number so it's safe to re-run. Existing accounts are never deleted; pass
   disable_unused_standard=1 to disable leaf accounts that are not in the FEDCO chart and have
   no ledger postings.

    bench --site <site> execute ng_compliance.setup.coa.import_chart \
        --kwargs "{'company': 'FEDCO West Africa Limited'}"
"""

import frappe

from ng_compliance.setup.profile import account_by_number, load, load_chart


def _root(company, root_type):
	roots = frappe.get_all(
		"Account",
		filters={"company": company, "root_type": root_type, "is_group": 1, "parent_account": ("is", "not set")},
		pluck="name",
		order_by="lft",
	)
	if roots:
		return roots[0]
	# company has no chart at all: create the root
	chart = load_chart()
	acc = frappe.get_doc({
		"doctype": "Account",
		"account_name": chart["roots"][root_type],
		"company": company,
		"is_group": 1,
		"root_type": root_type,
		"report_type": "Balance Sheet" if root_type in ("Asset", "Liability", "Equity") else "Profit and Loss",
	})
	acc.flags.ignore_mandatory = True
	acc.insert(ignore_permissions=True)
	return acc.name


def _find(company, number, name, is_group, log):
	"""Existing account by number, else by name (then stamp the FEDCO number on it)."""
	by_number = frappe.db.get_value(
		"Account", {"company": company, "account_number": number, "is_group": is_group}, "name"
	)
	if by_number:
		return by_number
	by_name = frappe.db.get_value(
		"Account", {"company": company, "account_name": name, "is_group": is_group},
		["name", "account_number"], as_dict=True,
	)
	if not by_name:
		return None
	if by_name.account_number:
		log.append(f"! {by_name.name} has number {by_name.account_number}, FEDCO uses {number}; left unchanged")
		return by_name.name
	try:
		from erpnext.accounts.doctype.account.account import update_account_number

		new_name = update_account_number(by_name.name, name, number)
		log.append(f"# numbered {by_name.name} -> {new_name}")
		return new_name or by_name.name
	except Exception as e:
		frappe.db.rollback()
		log.append(f"! could not number {by_name.name} as {number}: {e}")
		return by_name.name


@frappe.whitelist()
def import_chart(company, disable_unused_standard=0, set_defaults=1):
	frappe.only_for(("System Manager", "Accounts Manager"))
	chart = load_chart()
	currency = frappe.get_cached_value("Company", company, "default_currency")
	log, groups = [], {}

	for h in chart["headlines"]:
		existing = _find(company, h["code"], h["name"], 1, log)
		if existing:
			groups[h["code"]] = existing
			log.append(f"= {existing}")
			continue
		acc = frappe.get_doc({
			"doctype": "Account",
			"account_name": h["name"],
			"account_number": h["code"],
			"parent_account": _root(company, h["root_type"]),
			"company": company,
			"is_group": 1,
			"root_type": h["root_type"],
			"account_type": h["account_type"] or None,
		})
		acc.insert(ignore_permissions=True)
		groups[h["code"]] = acc.name
		log.append(f"+ {acc.name}")

	for a in chart["accounts"]:
		existing = _find(company, a["code"], a["name"], 0, log)
		if existing:
			log.append(f"= {existing}")
			continue
		acc = frappe.get_doc({
			"doctype": "Account",
			"account_name": a["name"],
			"account_number": a["code"],
			"parent_account": groups[a["headline"]],
			"company": company,
			"is_group": 0,
			"root_type": a["root_type"],
			"account_type": a["account_type"] or None,
			"account_currency": a["currency"] or currency,
		})
		if a["account_type"] == "Tax":
			acc.tax_rate = 7.5 if a["code"] in ("20013", "10021", "10022") else 0
		try:
			acc.insert(ignore_permissions=True)
			log.append(f"+ {acc.name}")
		except Exception as e:
			frappe.db.rollback()
			log.append(f"! {a['code']} {a['name']}: {e}")

	if int(disable_unused_standard):
		log += _disable_unused(company, chart)
	if int(set_defaults):
		log += set_company_defaults(company)
	frappe.db.commit()
	for line in log:
		print(line)
	print("\n".join(f"note: {n}" for n in chart.get("notes", [])))
	return log


def _disable_unused(company, chart):
	keep = {a["code"] for a in chart["accounts"]}
	log = []
	for acc in frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "disabled": 0},
		fields=["name", "account_number"],
	):
		if acc.account_number in keep:
			continue
		if frappe.db.exists("GL Entry", {"account": acc.name}):
			continue
		if _is_company_default(company, acc.name):
			continue
		frappe.db.set_value("Account", acc.name, "disabled", 1)
		log.append(f"- disabled {acc.name} (not in FEDCO chart, no postings)")
	return log


def _is_company_default(company, account):
	meta = frappe.get_meta("Company")
	fields = [f.fieldname for f in meta.fields if f.fieldtype == "Link" and f.options == "Account"]
	values = frappe.db.get_value("Company", company, fields, as_dict=True) or {}
	return account in values.values()


@frappe.whitelist()
def set_company_defaults(company):
	"""Point the company's default accounts at the FEDCO chart (one field at a time so a
	single validation error doesn't block the rest)."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	log = []
	profile = load()
	meta = frappe.get_meta("Company")
	for field, number in profile["accounts"]["company_defaults"].items():
		if not meta.has_field(field):
			continue
		acc = account_by_number(company, number)
		if not acc:
			log.append(f"! default {field}: account {number} not found")
			continue
		try:
			comp = frappe.get_doc("Company", company)
			comp.set(field, acc)
			comp.save(ignore_permissions=True)
			log.append(f"default {field} = {acc}")
		except Exception as e:
			frappe.db.rollback()
			log.append(f"! default {field}: {e}")

	details = profile.get("company_details", {})
	comp = frappe.get_doc("Company", company)
	changed = False
	for field, key in (("tax_id", "tax_id"), ("ng_rc_number", "rc_number"), ("ng_registered_address", "registered_address")):
		if meta.has_field(field) and details.get(key) and not comp.get(field):
			comp.set(field, details[key])
			changed = True
	if changed:
		comp.save(ignore_permissions=True)
		log.append("Company TIN / RC number / registered address filled from profile")
	frappe.db.commit()
	return log
