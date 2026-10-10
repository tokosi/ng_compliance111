"""Nigeria payroll setup for Frappe HR v16 (FEDCO payslip layout, NTA 2025 PAYE).

    bench --site <site> execute ng_compliance.setup.payroll.setup_nigeria_payroll \
        --kwargs "{'company': 'FEDCO West Africa Limited', 'year': 2026}"

Monthly amounts are entered PER EMPLOYEE on the Salary Structure Assignment (Basic, COLA,
Housing, Transport, Other allowances, NHIS/life premium, HMO premium). Entering only "Base"
puts the whole amount in Basic (as in the FEDCO sample payslip). Overtime, bonus and loan
recoveries are entered month by month as Additional Salary.

Rates come from data/fedco_profile.json -> payroll_parameters (the parameter sheet):
pension 8% / 10% of Basic+Housing+Transport, NHF 2.5% of Basic (opt-in per employee),
NSITF 1% and ITF 1% of emoluments, HMO N1,250/month, group life % of emoluments.

How PAYE is computed: HRMS annualises taxable earnings, subtracts deductions flagged
"Exempted from Income Tax" (Pension, NHF, NHIS/life premium) and approved exemptions
(Rent Relief), applies the NTA 2025 slab, then spreads the remaining annual tax over the
remaining months of the payroll period.
"""

import frappe
from frappe.utils import getdate

from ng_compliance.paye import NTA_2025_BANDS
from ng_compliance.setup.profile import account, params

SLAB_NAME = "Nigeria NTA 2025"
STRUCTURE_NAME = "Nigeria Monthly (NTA 2025)"
RENT_RELIEF = "Rent Relief"

EMOLUMENTS = "(B + COLA + HA + TA + OA)"
PENSIONABLE = "(B + HA + TA)"


def _pct(x):
	return f"{x:g}"


def components():
	"""(name, abbr, type, formula, condition, flags, accounts, in_structure)

	accounts: profile account key, or (expense key, liability key) for employer contributions.
	"""
	p = params()
	tax_earning = {"is_tax_applicable": 1, "depends_on_payment_days": 1, "remove_if_zero_valued": 1}
	one_off = {"is_tax_applicable": 1, "depends_on_payment_days": 0}
	rows = [
		("Basic Salary", "B", "Earning", "(ng_basic or 0)", "", tax_earning, "staff_costs", True),
		("Cost of Living Allowance", "COLA", "Earning", "(ng_cola or 0)", "", tax_earning, "staff_costs", True),
		("Housing Allowance", "HA", "Earning", "(ng_housing or 0)", "", tax_earning, "staff_costs", True),
		("Transport Allowance", "TA", "Earning", "(ng_transport or 0)", "", tax_earning, "staff_costs", True),
		("Other Allowances", "OA", "Earning", "(ng_other_allowance or 0)", "", tax_earning, "staff_costs", True),
		("Overtime", "OT", "Earning", "", "", one_off, "staff_costs", False),
		("Variable Pay / Bonus", "VP", "Earning", "", "", one_off, "staff_costs", False),
		("Employee Pension", "PEN", "Deduction", f"{PENSIONABLE} * {_pct(p['employee_pension_rate'])}", "",
			{"exempted_from_income_tax": 1, "depends_on_payment_days": 0}, "pension_payable", True),
		("National Housing Fund", "NHF", "Deduction", f"B * {_pct(p['nhf_rate'])}", "ng_nhf_opt_in",
			{"exempted_from_income_tax": 1, "depends_on_payment_days": 0, "remove_if_zero_valued": 1},
			"nhf_payable", True),
		("NHIS / Life Premium", "NHIS", "Deduction", "(ng_nhis_deduction or 0)", "",
			{"exempted_from_income_tax": 1, "depends_on_payment_days": 0, "remove_if_zero_valued": 1},
			"hmo_payable", True),
		("PAYE", "PAYE", "Deduction", "", "",
			{"variable_based_on_taxable_salary": 1, "is_income_tax_component": 1}, "paye_payable", True),
		("Loan / Other Deductions", "LOAN", "Deduction", "", "", {"depends_on_payment_days": 0}, "staff_loans", False),
		("Employer Pension", "EPEN", "Employer Contribution",
			f"{PENSIONABLE} * {_pct(p['employer_pension_rate'])}", "", {}, ("staff_costs", "pension_payable"), True),
		("NSITF Employer", "NSITF", "Employer Contribution", f"{EMOLUMENTS} * {_pct(p['nsitf_rate'])}", "", {},
			("staff_costs", "nsitf_payable"), True),
	]
	if p.get("itf_applicable"):
		rows.append(("ITF Employer", "ITF", "Employer Contribution", f"{EMOLUMENTS} * {_pct(p['itf_rate'])}", "", {},
			("staff_costs", "itf_payable"), True))
	if p.get("hmo_premium_monthly"):
		rows.append(("HMO Premium", "HMO", "Employer Contribution", "(ng_hmo_premium or 0)", "", {},
			("staff_costs", "hmo_payable"), True))
	if p.get("group_life_rate_of_annual_emoluments"):
		rows.append(("Group Life Assurance", "GLA", "Employer Contribution",
			f"{EMOLUMENTS} * {_pct(p['group_life_rate_of_annual_emoluments'])}", "", {},
			("staff_costs", "hmo_payable"), True))
	return rows


TABLE_FOR_TYPE = {"Earning": "earnings", "Deduction": "deductions", "Employer Contribution": "employer_contributions"}


def _has(doctype, field):
	return frappe.get_meta(doctype).has_field(field)


def _set_name(doc, name):
	"""Force a fixed document name regardless of the doctype's naming rule."""
	doc.name = name
	doc.set("__newname", name)
	doc.flags.name_set = True


@frappe.whitelist()
def setup_nigeria_payroll(company, year=2026):
	frappe.only_for(("System Manager", "HR Manager"))
	year = int(year)
	log = []
	log += create_components(company)
	log.append(create_income_tax_slab(company, year))
	log.append(create_payroll_period(company, year))
	log += create_rent_relief_category()
	log.append(create_salary_structure(company))
	frappe.db.commit()
	for line in log:
		print(line)
	return log


def _account_row(company, mapping):
	if isinstance(mapping, tuple):
		exp, liab = account(company, mapping[0]), account(company, mapping[1])
		missing = [k for k, a in zip(mapping, (exp, liab)) if not a]
		return ({"company": company, "account": exp, "liability_account": liab} if not missing else None), missing
	acc = account(company, mapping)
	return ({"company": company, "account": acc} if acc else None), ([] if acc else [mapping])


def create_components(company):
	log = []
	for name, abbr, ctype, formula, condition, flags, mapping, _in in components():
		if frappe.db.exists("Salary Component", name):
			doc = frappe.get_doc("Salary Component", name)
			action = "updated"
		else:
			doc = frappe.new_doc("Salary Component")
			doc.salary_component = name
			action = "created"
		doc.salary_component_abbr = abbr
		doc.type = ctype
		doc.amount_based_on_formula = 1 if formula else 0
		doc.formula = formula or None
		doc.condition = condition or None
		for k, v in flags.items():
			if _has("Salary Component", k):
				doc.set(k, v)
		row, missing = _account_row(company, mapping)
		if row:
			doc.set("accounts", [r for r in doc.get("accounts") or [] if r.company != company])
			doc.append("accounts", row)
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
		log.append(f"Salary Component {name}: {action}"
			+ (f" (missing accounts {missing}: run ng_compliance.setup.coa.import_chart first)" if missing else ""))
	return log


def create_income_tax_slab(company, year):
	if frappe.db.exists("Income Tax Slab", SLAB_NAME):
		return f"Income Tax Slab {SLAB_NAME}: exists"
	slab = frappe.new_doc("Income Tax Slab")
	_set_name(slab, SLAB_NAME)
	slab.effective_from = getdate("2026-01-01")
	if _has("Income Tax Slab", "company"):
		slab.company = company
	slab.currency = frappe.get_cached_value("Company", company, "default_currency") or "NGN"
	slab.standard_tax_exemption_amount = 0
	slab.allow_tax_exemption = 1
	# HRMS taxes each band as (to - from + 1), so later bands start at previous upper + 1
	lower = 0
	for upper, rate in NTA_2025_BANDS:
		slab.append("slabs", {
			"from_amount": lower + 1 if lower else 0,
			"to_amount": upper or 0,
			"percent_deduction": rate * 100,
		})
		lower = upper or lower
	slab.insert(ignore_permissions=True)
	slab.submit()
	return f"Income Tax Slab {SLAB_NAME}: created and submitted"


def create_payroll_period(company, year):
	name = f"Nigeria {year}"
	if frappe.db.exists("Payroll Period", name):
		return f"Payroll Period {name}: exists"
	pp = frappe.new_doc("Payroll Period")
	_set_name(pp, name)
	pp.company = company
	pp.start_date = getdate(f"{year}-01-01")
	pp.end_date = getdate(f"{year}-12-31")
	pp.insert(ignore_permissions=True)
	return f"Payroll Period {name}: created"


def create_rent_relief_category():
	cap = params()["rent_relief_cap"]
	log = []
	if not frappe.db.exists("Employee Tax Exemption Category", RENT_RELIEF):
		c = frappe.new_doc("Employee Tax Exemption Category")
		_set_name(c, RENT_RELIEF)
		c.max_amount = cap
		c.is_active = 1
		c.insert(ignore_permissions=True)
		log.append("Tax Exemption Category Rent Relief: created")
	if not frappe.db.exists("Employee Tax Exemption Sub Category", RENT_RELIEF):
		s = frappe.new_doc("Employee Tax Exemption Sub Category")
		_set_name(s, RENT_RELIEF)
		s.exemption_category = RENT_RELIEF
		s.max_amount = cap
		s.is_active = 1
		s.insert(ignore_permissions=True)
		log.append("Tax Exemption Sub Category Rent Relief: created")
	return log or ["Rent Relief exemption: exists"]


def create_salary_structure(company):
	if frappe.db.exists("Salary Structure", STRUCTURE_NAME):
		return f"Salary Structure {STRUCTURE_NAME}: exists (cancel & amend it to change)"
	ss = frappe.new_doc("Salary Structure")
	_set_name(ss, STRUCTURE_NAME)
	ss.company = company
	ss.payroll_frequency = "Monthly"
	ss.currency = frappe.get_cached_value("Company", company, "default_currency") or "NGN"
	ss.is_active = "Yes"
	for name, abbr, ctype, formula, condition, flags, _m, in_structure in components():
		if not in_structure:
			continue
		row = {"salary_component": name, "abbr": abbr}
		if formula:
			row.update({"amount_based_on_formula": 1, "formula": formula})
		if condition:
			row["condition"] = condition
		row.update({k: v for k, v in flags.items() if k != "remove_if_zero_valued"})
		ss.append(TABLE_FOR_TYPE[ctype], row)
	ss.insert(ignore_permissions=True)
	ss.submit()
	return f"Salary Structure {STRUCTURE_NAME}: created and submitted"


@frappe.whitelist()
def assign_structure(employee, from_date, basic, cola=0, housing=0, transport=0, other_allowance=0,
		nhis_deduction=0, hmo_premium=None, exchange_rate=0, company=None):
	"""Create + submit a Salary Structure Assignment with the monthly amounts."""
	frappe.only_for(("System Manager", "HR Manager"))
	company = company or frappe.db.get_value("Employee", employee, "company")
	ssa = frappe.new_doc("Salary Structure Assignment")
	ssa.update({
		"employee": employee,
		"salary_structure": STRUCTURE_NAME,
		"company": company,
		"from_date": getdate(from_date),
		"income_tax_slab": SLAB_NAME,
		"ng_basic": float(basic),
		"ng_cola": float(cola),
		"ng_housing": float(housing),
		"ng_transport": float(transport),
		"ng_other_allowance": float(other_allowance),
		"ng_nhis_deduction": float(nhis_deduction),
		"ng_hmo_premium": float(params()["hmo_premium_monthly"] if hmo_premium is None else hmo_premium),
		"ng_exchange_rate": float(exchange_rate),
	})
	ssa.insert(ignore_permissions=True)
	ssa.submit()
	return ssa.name
