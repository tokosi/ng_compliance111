"""PAYE (by State IRS), Pension (by PFA), NHF, NSITF and ITF remittance schedule
from submitted Salary Slips in the period."""

import frappe
from frappe import _
from frappe.utils import flt

COMPONENT_COLUMNS = [
	("PAYE", "paye", "PAYE"),
	("Employee Pension", "pension_ee", "Pension (Employee 8%)"),
	("Employer Pension", "pension_er", "Pension (Employer 10%)"),
	("National Housing Fund", "nhf", "NHF"),
	("NSITF Employer", "nsitf", "NSITF"),
	("ITF Employer", "itf", "ITF"),
	("NHIS / Life Premium", "nhis", "NHIS / Life (Employee)"),
	("HMO Premium", "hmo", "HMO (Employer)"),
	("Group Life Assurance", "gla", "Group Life (Employer)"),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)
	if filters.group_by_state:
		return state_columns(), summarise(rows)
	return employee_columns(), rows


def currency(fieldname, label, width=130):
	return {"fieldname": fieldname, "label": _(label), "fieldtype": "Currency", "width": width}


def employee_columns():
	cols = [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "paye_state", "label": _("PAYE State"), "fieldtype": "Data", "width": 110},
		{"fieldname": "tin", "label": _("TIN"), "fieldtype": "Data", "width": 110},
		{"fieldname": "pfa", "label": _("PFA"), "fieldtype": "Data", "width": 120},
		{"fieldname": "rsa_pin", "label": _("RSA PIN"), "fieldtype": "Data", "width": 120},
		currency("gross_pay", "Gross Pay"),
	]
	cols += [currency(f, l) for _c, f, l in COMPONENT_COLUMNS]
	return cols


def state_columns():
	return [
		{"fieldname": "paye_state", "label": _("PAYE State"), "fieldtype": "Data", "width": 150},
		{"fieldname": "headcount", "label": _("Employees"), "fieldtype": "Int", "width": 100},
		currency("gross_pay", "Gross Pay", 150),
	] + [currency(f, l, 150) for _c, f, l in COMPONENT_COLUMNS]


def get_rows(filters):
	conditions = {"company": filters.company, "docstatus": 1,
		"start_date": (">=", filters.from_date), "end_date": ("<=", filters.to_date)}
	slips = frappe.get_all("Salary Slip", filters=conditions,
		fields=["name", "employee", "employee_name", "gross_pay"])
	if not slips:
		return []
	emp_fields = ["name", "ng_paye_state", "ng_tax_id", "ng_pfa", "ng_rsa_pin"]
	meta = frappe.get_meta("Employee")
	emp_fields = [f for f in emp_fields if f == "name" or meta.has_field(f)]
	emps = {e.name: e for e in frappe.get_all("Employee",
		filters={"name": ("in", list({s.employee for s in slips}))}, fields=emp_fields)}
	details = frappe.get_all("Salary Detail",
		filters={"parenttype": "Salary Slip", "parent": ("in", [s.name for s in slips])},
		fields=["parent", "salary_component", "amount"])
	comp_map = {c: f for c, f, _l in COMPONENT_COLUMNS}

	by_emp = {}
	for s in slips:
		e = emps.get(s.employee, frappe._dict())
		row = by_emp.setdefault(s.employee, frappe._dict(
			employee=s.employee, employee_name=s.employee_name,
			paye_state=e.get("ng_paye_state") or _("Not set"), tin=e.get("ng_tax_id"),
			pfa=e.get("ng_pfa"), rsa_pin=e.get("ng_rsa_pin"), gross_pay=0,
			**{f: 0 for _c, f, _l in COMPONENT_COLUMNS}))
		row.gross_pay += flt(s.gross_pay)
	slip_emp = {s.name: s.employee for s in slips}
	for d in details:
		f = comp_map.get(d.salary_component)
		if f:
			by_emp[slip_emp[d.parent]][f] += flt(d.amount)

	rows = list(by_emp.values())
	if filters.paye_state:
		rows = [r for r in rows if r.paye_state == filters.paye_state]
	return sorted(rows, key=lambda r: (r.paye_state, r.employee))


def summarise(rows):
	out = {}
	for r in rows:
		s = out.setdefault(r.paye_state, frappe._dict(paye_state=r.paye_state, headcount=0, gross_pay=0,
			**{f: 0 for _c, f, _l in COMPONENT_COLUMNS}))
		s.headcount += 1
		s.gross_pay += r.gross_pay
		for _c, f, _l in COMPONENT_COLUMNS:
			s[f] += r[f]
	return list(out.values())
