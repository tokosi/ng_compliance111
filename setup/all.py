"""One-shot setup: chart of accounts -> VAT/WHT -> payroll -> ESS.

    bench --site <site> execute ng_compliance.setup.all.run \
        --kwargs "{'company': 'FEDCO West Africa Limited'}"
"""

import frappe

from ng_compliance.setup.accounts import setup_nigeria_accounts
from ng_compliance.setup.coa import import_chart
from ng_compliance.setup.ess import setup_ess
from ng_compliance.setup.payroll import setup_nigeria_payroll


@frappe.whitelist()
def run(company, year=2026, wht=1, create_employee_users=1, send_welcome_email=0, disable_unused_standard=0):
	frappe.only_for("System Manager")
	print("== Chart of accounts ==")
	import_chart(company, disable_unused_standard=disable_unused_standard)
	print("== VAT / WHT ==")
	setup_nigeria_accounts(company, wht=wht)
	print("== Payroll ==")
	setup_nigeria_payroll(company, year=year)
	print("== Employee Self Service ==")
	setup_ess(company, send_welcome_email=send_welcome_email, create_employee_users=create_employee_users)
	return "done"
