"""Employee Self Service (ESS) setup for Frappe HR v16.

Employees use the Frappe HR mobile/PWA app at https://<your-site>/hrms (installable on
phones) to apply for leave, file expense claims, check in, view and download salary slips,
and submit rent declarations for PAYE rent relief.

Run:
    bench --site <site> execute ng_compliance.setup.ess.setup_ess \
        --kwargs "{'company': 'Acme Nigeria Ltd', 'send_welcome_email': 0}"

What it does (idempotently):
  * HR Settings / Payroll Settings sensible defaults for ESS (guarded: only fields that exist)
  * Makes sure HRMS's "Employee Self Service" User Type exists (limited, non-desk-licence user
    type that already allows leave, expenses, advances, attendance requests, salary slips
    and tax exemption declaration/proof - i.e. rent relief claims)
  * Creates an ESS User for every active employee with an email and no linked user and links
    it to the Employee, so they only ever see their own records
"""

import frappe

ESS_USER_TYPE = "Employee Self Service"
ESS_ROLE = "Employee Self Service"

HR_SETTINGS = {
	"leave_approver_mandatory_in_leave_application": 1,
	"expense_approver_mandatory_in_expense_claim": 1,
	"send_leave_notification": 1,
	"allow_employee_checkin_from_mobile_app": 1,
	"prevent_self_leave_approval": 1,
	"prevent_self_expense_approval": 1,
	"show_leaves_of_all_department_members_in_calendar": 0,
	"role_allowed_to_create_backdated_leave_application": "HR Manager",
	"restrict_backdated_leave_application": 1,
}

PAYROLL_SETTINGS = {
	"payroll_based_on": "Leave",
	"email_salary_slip_to_employee": 1,
	"encrypt_salary_slips_in_emails": 1,
	"password_policy": "{first_name}{date_of_birth.year}",
	"show_leave_balances_in_salary_slip": 1,
	"process_payroll_accounting_entry_based_on_employee": 1,
}

def _set_singles(doctype, values, log):
	meta = frappe.get_meta(doctype)
	for field, value in values.items():
		if meta.has_field(field):
			frappe.db.set_single_value(doctype, field, value)
			log.append(f"{doctype}.{field} = {value}")


def ensure_ess_user_type(log):
	"""HRMS v16 ships an 'Employee Self Service' User Type (role + allowed doctypes,
	including Tax Exemption Declaration/Proof). Recreate it if it's missing."""
	if not frappe.db.exists("User Type", ESS_USER_TYPE):
		from hrms.setup import add_non_standard_user_types

		add_non_standard_user_types()
		log.append("Created HRMS 'Employee Self Service' user type")
	else:
		log.append("HRMS 'Employee Self Service' user type present")


def _employee_email(emp):
	return emp.get("prefered_email") or emp.get("company_email") or emp.get("personal_email")


def create_users(company=None, send_welcome_email=0, log=None):
	log = log if log is not None else []
	filters = {"status": "Active", "user_id": ("is", "not set")}
	if company:
		filters["company"] = company
	employees = frappe.get_all(
		"Employee",
		filters=filters,
		fields=["name", "first_name", "last_name", "prefered_email", "company_email", "personal_email"],
	)
	for emp in employees:
		email = _employee_email(emp)
		if not email:
			log.append(f"{emp.name}: no email, skipped")
			continue
		if frappe.db.exists("User", email):
			user = frappe.get_doc("User", email)
		else:
			user = frappe.new_doc("User")
			user.email = email
			user.first_name = emp.first_name
			user.last_name = emp.last_name
			user.user_type = ESS_USER_TYPE
			user.send_welcome_email = int(send_welcome_email)
			user.insert(ignore_permissions=True)
		if user.user_type == ESS_USER_TYPE:
			user.add_roles(ESS_ROLE)
		else:
			# existing desk user (e.g. a manager who is also an employee): keep their type
			user.add_roles("Employee", ESS_ROLE)
		# Linking user_id makes HRMS create the Employee User Permission (own-record access)
		emp_doc = frappe.get_doc("Employee", emp.name)
		emp_doc.user_id = user.name
		if emp_doc.meta.has_field("create_user_permission"):
			emp_doc.create_user_permission = 1
		emp_doc.save(ignore_permissions=True)
		log.append(f"{emp.name}: user {user.name} ({user.user_type}) linked")
	return log


@frappe.whitelist()
def setup_ess(company=None, send_welcome_email=0, create_employee_users=1):
	frappe.only_for(("System Manager", "HR Manager"))
	log = []
	_set_singles("HR Settings", HR_SETTINGS, log)
	_set_singles("Payroll Settings", PAYROLL_SETTINGS, log)
	ensure_ess_user_type(log)
	if int(create_employee_users):
		create_users(company, send_welcome_email, log)
	frappe.db.commit()
	for line in log:
		print(line)
	return log
