"""Monthly VAT return worksheet (NRS form VAT 002), due by the 21st of the following month.

Supplies come from submitted Sales Invoices grouped by their VAT template; VAT amounts come
from the general ledger on the VAT accounts in data/fedco_profile.json.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, getdate

from ng_compliance.setup.profile import account


def execute(filters=None):
	f = frappe._dict(filters or {})
	columns = [
		{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 60},
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 420},
		{"fieldname": "amount", "label": _("Amount (₦)"), "fieldtype": "Currency", "width": 180},
	]
	return columns, get_data(f)


def _supplies(f, template_like):
	return flt(frappe.db.sql(
		"""select sum(base_net_total) from `tabSales Invoice`
		where docstatus = 1 and company = %(company)s and posting_date between %(from_date)s and %(to_date)s
		and ifnull(taxes_and_charges, '') like %(t)s""",
		{**f, "t": template_like},
	)[0][0])


def _gl(f, accounts, voucher_type=None, credit_minus_debit=True):
	accounts = [a for a in accounts if a]
	if not accounts:
		return 0
	cond = "and voucher_type = %(vt)s" if voucher_type else ""
	expr = "credit - debit" if credit_minus_debit else "debit - credit"
	return flt(frappe.db.sql(
		f"""select sum({expr}) from `tabGL Entry`
		where is_cancelled = 0 and company = %(company)s and account in %(accounts)s
		and posting_date between %(from_date)s and %(to_date)s {cond}""",
		{**f, "accounts": tuple(accounts), "vt": voucher_type},
	)[0][0])


def get_data(f):
	c = f.company
	out_acc = account(c, "vat_output")
	in_accs = [account(c, "vat_input_local"), account(c, "vat_input_import")]

	total = flt(frappe.db.sql(
		"""select sum(base_net_total) from `tabSales Invoice` where docstatus = 1 and company = %(company)s
		and posting_date between %(from_date)s and %(to_date)s""", f)[0][0])
	exempt = _supplies(f, "NG VAT Exempt%")
	zero = _supplies(f, "NG VAT Zero-Rated%")
	taxable = total - exempt - zero

	output_sales = _gl(f, [out_acc], "Sales Invoice")
	output_total = _gl(f, [out_acc])
	self_charged = output_total - output_sales  # reverse charge on non-resident supplies, journals
	input_vat = _gl(f, in_accs, credit_minus_debit=False)
	net = output_total - input_vat
	due = getdate(add_months(get_first_day(f.to_date), 1)).replace(day=21)

	rows = [
		("1", _("Total value of supplies (sales, net of VAT)"), total),
		("2", _("Less: exempt supplies"), exempt),
		("3", _("Less: zero-rated supplies (exports)"), zero),
		("4", _("Taxable supplies at 7.5%  (1 - 2 - 3)"), taxable),
		("5", _("Output VAT on sales"), output_sales),
		("6", _("VAT self-charged / withheld (non-resident supplies, adjustments)"), self_charged),
		("7", _("Total output VAT  (5 + 6)"), output_total),
		("8", _("Less: recoverable input VAT (local, imports, capex & services)"), input_vat),
		("9", _("VAT payable / (refundable)  (7 - 8)"), net),
	]
	data = [{"line": l, "description": d, "amount": a, "bold": l in ("4", "7", "9")} for l, d, a in rows]
	data.append({"line": "", "description": _("Return (VAT 002) and payment due by {0}").format(
		frappe.utils.formatdate(due)), "amount": None})
	if not out_acc or not all(in_accs):
		data.append({"line": "!", "description": _("VAT accounts not found - run the chart of accounts import"),
			"amount": None})
	return data
