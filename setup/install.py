import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

NIGERIAN_STATES = (
	"\nAbia\nAdamawa\nAkwa Ibom\nAnambra\nBauchi\nBayelsa\nBenue\nBorno\nCross River\nDelta\n"
	"Ebonyi\nEdo\nEkiti\nEnugu\nFCT Abuja\nGombe\nImo\nJigawa\nKaduna\nKano\nKatsina\nKebbi\n"
	"Kogi\nKwara\nLagos\nNasarawa\nNiger\nOgun\nOndo\nOsun\nOyo\nPlateau\nRivers\nSokoto\n"
	"Taraba\nYobe\nZamfara"
)


def after_install():
	create_custom_fields_ng()
	set_default_print_formats()
	frappe.db.commit()


def after_migrate():
	create_custom_fields_ng()
	set_default_print_formats()


def _money(fieldname, label, insert_after, description=None, default="0"):
	f = {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "insert_after": insert_after,
		"default": default, "options": "currency"}
	if description:
		f["description"] = description
	return f


def custom_fields():
	from ng_compliance.setup.profile import params

	hmo = str(params().get("hmo_premium_monthly") or 0)
	return {
		"Employee": [
			{"fieldname": "ng_statutory_section", "label": "Nigeria Statutory", "fieldtype": "Section Break",
				"insert_after": "bank_ac_no", "collapsible": 1},
			{"fieldname": "ng_staff_type", "label": "Staff Type", "fieldtype": "Select",
				"options": "Local\nExpatriate", "default": "Local", "insert_after": "ng_statutory_section"},
			{"fieldname": "ng_tax_id", "label": "Tax ID (TIN)", "fieldtype": "Data", "insert_after": "ng_staff_type"},
			{"fieldname": "ng_paye_state", "label": "PAYE State (State of Residence)", "fieldtype": "Select",
				"options": NIGERIAN_STATES, "insert_after": "ng_tax_id",
				"description": "PAYE is remitted to the State IRS where the employee resides."},
			{"fieldname": "ng_tax_office", "label": "Tax Office", "fieldtype": "Data", "insert_after": "ng_paye_state",
				"description": "Filled from the PAYE state if left blank (e.g. Ondo → ODIRS)."},
			{"fieldname": "ng_col_break", "fieldtype": "Column Break", "insert_after": "ng_tax_office"},
			{"fieldname": "ng_pfa", "label": "Pension Fund Administrator (PFA)", "fieldtype": "Data",
				"insert_after": "ng_col_break"},
			{"fieldname": "ng_rsa_pin", "label": "RSA PIN", "fieldtype": "Data", "insert_after": "ng_pfa"},
			{"fieldname": "ng_nhf_opt_in", "label": "NHF Opt-in (2.5% of Basic)", "fieldtype": "Check",
				"default": "0", "insert_after": "ng_rsa_pin"},
			{"fieldname": "ng_nhf_number", "label": "NHF Number", "fieldtype": "Data", "insert_after": "ng_nhf_opt_in",
				"depends_on": "ng_nhf_opt_in"},
		],
		"Salary Structure Assignment": [
			{"fieldname": "ng_pay_section", "label": "Monthly Pay (Nigeria)", "fieldtype": "Section Break",
				"insert_after": "variable",
				"description": "Monthly amounts. Leave all blank and fill Base to pay everything as Basic. "
				"Base is recalculated as the total of these."},
			_money("ng_basic", "Basic Salary", "ng_pay_section"),
			_money("ng_cola", "Cost of Living Allowance", "ng_basic"),
			_money("ng_housing", "Housing Allowance", "ng_cola"),
			_money("ng_transport", "Transport Allowance", "ng_housing"),
			_money("ng_other_allowance", "Other Allowances", "ng_transport"),
			{"fieldname": "ng_pay_col", "fieldtype": "Column Break", "insert_after": "ng_other_allowance"},
			_money("ng_nhis_deduction", "NHIS / Life Premium (employee)", "ng_pay_col",
				"Deducted monthly and allowed against PAYE."),
			_money("ng_hmo_premium", "HMO Premium (employer)", "ng_nhis_deduction", default=hmo),
			{"fieldname": "ng_exchange_rate", "label": "Exchange Rate (₦/$)", "fieldtype": "Float",
				"insert_after": "ng_hmo_premium", "default": "0",
				"description": "Expatriates on USD-referenced pay: shown on the payslip."},
		],
		"Company": [
			{"fieldname": "ng_rc_number", "label": "RC Number (CAC)", "fieldtype": "Data", "insert_after": "tax_id"},
			{"fieldname": "ng_registered_address", "label": "Registered Address", "fieldtype": "Small Text",
				"insert_after": "ng_rc_number", "description": "Printed on payslips and VAT invoices."},
		],
		"Sales Invoice": [
			{"fieldname": "ng_nrs_irn", "label": "NRS Invoice Reference (IRN)", "fieldtype": "Data",
				"insert_after": "tax_id", "allow_on_submit": 1, "no_copy": 1,
				"description": "Reference/IRN returned by the NRS fiscalisation (e-invoicing) system. Printed on the VAT invoice."},
		],
		"Employee Tax Exemption Declaration Category": [
			{"fieldname": "ng_annual_rent", "label": "Annual Rent Paid (NGN)", "fieldtype": "Currency",
				"insert_after": "exemption_category", "in_list_view": 1,
				"description": "For Rent Relief: relief = 20% of rent, capped at N500,000 (computed automatically)."}
		],
		"Employee Tax Exemption Proof Submission Detail": [
			{"fieldname": "ng_annual_rent", "label": "Annual Rent Paid (NGN)", "fieldtype": "Currency",
				"insert_after": "exemption_category", "in_list_view": 1}
		],
	}


def create_custom_fields_ng():
	fields = {dt: f for dt, f in custom_fields().items() if frappe.db.exists("DocType", dt)}
	create_custom_fields(fields, update=True)


def set_default_print_formats():
	"""Make the app's print formats the default for their doctypes (only if they exist and the
	site hasn't chosen another default)."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype, fmt in (("Salary Slip", "Nigeria Payslip"), ("Sales Invoice", "Nigeria VAT Invoice")):
		if not frappe.db.exists("Print Format", fmt):
			continue
		current = frappe.db.get_value(
			"Property Setter", {"doc_type": doctype, "property": "default_print_format"}, "value"
		)
		if current and current != fmt:
			continue
		make_property_setter(doctype, None, "default_print_format", fmt, "Data", for_doctype=True,
			validate_fields_for_doctype=False)
