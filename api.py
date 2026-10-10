"""Whitelisted helpers."""

import frappe
from frappe.utils import flt

from ng_compliance.paye import compute_annual_paye


@frappe.whitelist()
def paye_preview(monthly_gross, monthly_basic=0, monthly_housing=0, monthly_transport=0, annual_rent=0,
		include_pension=1, include_nhf=1):
	"""Independent NTA 2025 PAYE estimate, for checking payroll output.
	/api/method/ng_compliance.api.paye_preview?monthly_gross=500000&monthly_basic=200000..."""
	return compute_annual_paye(
		flt(monthly_gross) * 12,
		annual_basic=flt(monthly_basic) * 12,
		annual_housing=flt(monthly_housing) * 12,
		annual_transport=flt(monthly_transport) * 12,
		annual_rent=flt(annual_rent),
		include_pension=int(include_pension),
		include_nhf=int(include_nhf),
	)
