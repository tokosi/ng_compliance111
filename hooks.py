app_name = "ng_compliance"
app_title = "NG Compliance"
app_publisher = "FEDCO West Africa Limited"
app_description = "Nigeria PAYE (NTA 2025), statutory deductions, Nigerian accounting setup and ESS for ERPNext/Frappe HR v16"
app_email = "admin@example.com"
app_license = "MIT"

required_apps = ["erpnext", "hrms"]

after_install = "ng_compliance.setup.install.after_install"
after_migrate = "ng_compliance.setup.install.after_migrate"

doc_events = {
	"Employee Tax Exemption Declaration": {
		"before_validate": "ng_compliance.overrides.tax_exemption.apply_rent_relief_rule",
	},
	"Employee Tax Exemption Proof Submission": {
		"before_validate": "ng_compliance.overrides.tax_exemption.apply_rent_relief_rule",
	},
	"Salary Structure Assignment": {
		"before_validate": "ng_compliance.overrides.salary_structure_assignment.sync_base",
	},
	"Employee": {
		"validate": "ng_compliance.overrides.employee.set_tax_office",
	},
}

# Helpers available inside print formats (payslip + VAT invoice)
jinja = {
	"methods": [
		"ng_compliance.utils.print_helpers.ng_payslip",
		"ng_compliance.utils.print_helpers.ng_company",
		"ng_compliance.utils.print_helpers.ng_money",
		"ng_compliance.utils.print_helpers.ng_vat_invoice",
		"ng_compliance.utils.print_helpers.ng_logo_url",
	]
}

fixtures = []
