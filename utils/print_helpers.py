"""Jinja helpers for the Nigeria Payslip and Nigeria VAT Invoice print formats (see hooks.jinja)."""

import base64
import os
from functools import lru_cache

import frappe
from frappe.utils import cint, flt, formatdate, getdate

LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "images", "fedco-logo.png")


def _params():
	from ng_compliance.setup.profile import params

	return params()


def _pc(x):
	return f"{x * 100:g}%"


def payslip_layout():
	"""Rows always shown on the payslip, in order (label, salary component)."""
	p = _params()
	earnings = [
		("Basic salary", "Basic Salary"),
		("Cost of living allowance", "Cost of Living Allowance"),
		("Housing allowance", "Housing Allowance"),
		("Transport allowance", "Transport Allowance"),
		("Overtime", "Overtime"),
		("Other allowances", "Other Allowances"),
		("Variable pay / bonus", "Variable Pay / Bonus"),
	]
	deductions = [
		(f"Employee pension ({_pc(p['employee_pension_rate'])})", "Employee Pension"),
		(f"NHF ({_pc(p['nhf_rate'])}, opt-in)", "National Housing Fund"),
		("NHIS / life premium", "NHIS / Life Premium"),
		("PAYE income tax", "PAYE"),
		("Loan / other deductions", "Loan / Other Deductions"),
	]
	employer = [
		(f"Employer pension ({_pc(p['employer_pension_rate'])})", "Employer Pension"),
		(f"NSITF ({_pc(p['nsitf_rate'])})", "NSITF Employer"),
		(f"ITF ({_pc(p['itf_rate'])})", "ITF Employer"),
		("HMO premium", "HMO Premium"),
		("Group life assurance", "Group Life Assurance"),
	]
	return earnings, deductions, employer


def ng_money(value, dash=True, symbol=""):
	v = flt(value, 2)
	if dash and not v:
		return "-"
	s = f"{abs(v):,.2f}"
	return f"{'-' if v < 0 else ''}{symbol}{s}"


@lru_cache
def _logo_data_uri():
	try:
		with open(LOGO_PATH, "rb") as f:
			return "data:image/png;base64," + base64.b64encode(f.read()).decode()
	except OSError:
		return ""


def ng_logo_url():
	"""Logo embedded as a data URI so it survives PDF generation and emailed payslips."""
	return _logo_data_uri()


def ng_company(company):
	c = frappe.get_cached_doc("Company", company)
	address = c.get("ng_registered_address")
	if not address:
		try:
			from erpnext.setup.doctype.company.company import get_default_company_address

			addr_name = get_default_company_address(company)
			if addr_name:
				a = frappe.get_cached_doc("Address", addr_name)
				address = ", ".join(x for x in (a.address_line1, a.address_line2, a.city, a.state, a.country) if x)
		except Exception:
			address = ""
	return frappe._dict(
		name=c.company_name,
		address=(address or "").replace("\n", ", "),
		rc_number=c.get("ng_rc_number"),
		tax_id=c.get("tax_id"),
		logo=ng_logo_url(),
	)


def _clean(link_value):
	"""'Operations - FWA' -> 'Operations'"""
	return (link_value or "").rsplit(" - ", 1)[0] if link_value and " - " in link_value else (link_value or "")


def _rows(layout, table):
	amounts = {}
	for d in table or []:
		amounts[d.salary_component] = amounts.get(d.salary_component, 0) + flt(d.amount)
	listed = {comp for _l, comp in layout}
	rows = [frappe._dict(label=label, amount=amounts.get(comp, 0)) for label, comp in layout]
	rows += [frappe._dict(label=comp, amount=amt) for comp, amt in amounts.items() if comp not in listed]
	return rows


def _rent_relief_annual(employee, company, on_date):
	period = frappe.db.get_value(
		"Payroll Period",
		{"company": company, "start_date": ("<=", on_date), "end_date": (">=", on_date)},
		"name",
	)
	if not period:
		return 0
	for parent_dt, child_dt in (
		("Employee Tax Exemption Proof Submission", "Employee Tax Exemption Proof Submission Detail"),
		("Employee Tax Exemption Declaration", "Employee Tax Exemption Declaration Category"),
	):
		parents = frappe.get_all(parent_dt, filters={"employee": employee, "payroll_period": period, "docstatus": 1},
			pluck="name")
		if parents:
			return flt(sum(
				flt(r.amount) for r in frappe.get_all(child_dt,
					filters={"parent": ("in", parents), "exemption_sub_category": "Rent Relief"}, fields=["amount"])
			))
	return 0


def _ssa_exchange_rate(employee, on_date):
	ssa = frappe.get_all(
		"Salary Structure Assignment",
		filters={"employee": employee, "docstatus": 1, "from_date": ("<=", on_date)},
		fields=["name"], order_by="from_date desc", limit=1,
	)
	if not ssa or not frappe.get_meta("Salary Structure Assignment").has_field("ng_exchange_rate"):
		return 0
	return flt(frappe.db.get_value("Salary Structure Assignment", ssa[0].name, "ng_exchange_rate"))


def ng_payslip(doc):
	"""Everything the payslip template needs, from a Salary Slip."""
	emp = frappe.get_cached_doc("Employee", doc.employee)
	earnings_layout, deductions_layout, employer_layout = payslip_layout()
	start = getdate(doc.start_date)
	gross = flt(doc.gross_pay)
	paye = sum(flt(d.amount) for d in doc.deductions or [] if d.salary_component == "PAYE")
	tax_free = sum(flt(d.amount) for d in doc.deductions or [] if cint(d.get("exempted_from_income_tax")))
	rent_relief_m = flt(_rent_relief_annual(doc.employee, doc.company, start) / 12, 2)
	rate = _ssa_exchange_rate(doc.employee, start)

	return frappe._dict(
		company=ng_company(doc.company),
		period=start.strftime("%B %Y"),
		paid_on=formatdate(doc.posting_date, "dd-MMM-yyyy"),
		info_left=[
			("Employee ID", doc.employee),
			("Name", doc.employee_name),
			("Staff type", emp.get("ng_staff_type") or "Local"),
			("PAYE state", emp.get("ng_paye_state") or "-"),
			("TIN", emp.get("ng_tax_id") or "-"),
			("Bank", emp.get("bank_name") or "-"),
			("Account no.", emp.get("bank_ac_no") or "-"),
		],
		info_right=[
			("Department", _clean(doc.get("department") or emp.get("department")) or "-"),
			("Position", doc.get("designation") or emp.get("designation") or "-"),
			("Work location", _clean(doc.get("branch") or emp.get("branch")) or "-"),
			("Tax office", emp.get("ng_tax_office") or "-"),
			("PFA", emp.get("ng_pfa") or "-"),
			("RSA PIN", emp.get("ng_rsa_pin") or "-"),
			("Exchange rate (₦/$)", f"{rate:,.2f}" if rate else "N/A"),
		],
		earnings=_rows(earnings_layout, doc.earnings),
		deductions=_rows(deductions_layout, doc.deductions),
		employer=[r for r in _rows(employer_layout, doc.get("employer_contributions")) if r.amount],
		gross=gross,
		total_deductions=flt(doc.total_deduction),
		net=flt(doc.net_pay),
		net_in_words=doc.get("total_in_words"),
		working_days=doc.get("total_working_days"),
		payment_days=doc.get("payment_days"),
		memo=frappe._dict(
			rent_relief=rent_relief_m,
			chargeable=max(gross - tax_free - rent_relief_m, 0),
			effective_rate=(paye / gross * 100) if gross else 0,
		),
	)


def ng_vat_invoice(doc):
	"""VAT lines and treatment for the Nigeria VAT Invoice (NRS VAT invoice requirements)."""
	vat_rows = [t for t in doc.taxes or [] if "VAT" in (t.description or "") or "VAT" in (t.account_head or "")]
	vat = sum(flt(t.tax_amount_after_discount_amount or t.tax_amount) for t in vat_rows)
	base_vat = sum(flt(t.base_tax_amount_after_discount_amount or t.base_tax_amount) for t in vat_rows)
	rates = sorted({flt(t.rate) for t in vat_rows})
	template = doc.get("taxes_and_charges") or ""
	if "Zero-Rated" in template:
		treatment = "Zero-rated supply (export) – VAT 0%"
	elif "Exempt" in template:
		treatment = "VAT-exempt supply"
	elif vat_rows:
		treatment = "Standard-rated supply – VAT " + ", ".join(f"{r:g}%" for r in rates)
	else:
		treatment = "No VAT charged"
	customer_tin = doc.get("tax_id") or frappe.db.get_value("Customer", doc.customer, "tax_id")
	return frappe._dict(
		company=ng_company(doc.company),
		vat=vat,
		rates=rates,
		treatment=treatment,
		customer_tin=customer_tin,
		net=flt(doc.net_total),
		gross=flt(doc.grand_total),
		currency=doc.currency,
		base_vat=base_vat,
	)
