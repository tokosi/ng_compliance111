"""Runs on before_validate, so HRMS recomputes its totals from the corrected amounts.

Enforce NTA 2025 rent relief: 20% of annual rent paid, capped at N500,000.

Applies to rows on Employee Tax Exemption Declaration / Proof Submission whose
category or sub-category is the one created by setup (default "Rent Relief").
"""

import frappe
from frappe.utils import flt

from ng_compliance.paye import RENT_RELIEF_CAP, RENT_RELIEF_RATE, rent_relief

RENT_RELIEF_NAME = "Rent Relief"


def _is_rent_row(row):
	return RENT_RELIEF_NAME in (row.get("exemption_category"), row.get("exemption_sub_category"))


def apply_rent_relief_rule(doc, method=None):
	table = "declarations" if doc.doctype == "Employee Tax Exemption Declaration" else "tax_exemption_proofs"
	changed = False
	for row in doc.get(table) or []:
		if not _is_rent_row(row):
			continue
		rent = flt(row.get("ng_annual_rent"))
		if not rent:
			frappe.throw(
				frappe._("Row {0}: enter Annual Rent Paid to claim Rent Relief.").format(row.idx),
				title=frappe._("Rent Relief"),
			)
		allowed = rent_relief(rent, RENT_RELIEF_RATE, RENT_RELIEF_CAP)
		if flt(row.amount) != allowed:
			row.amount = allowed
			changed = True
	if changed:
		frappe.msgprint(
			frappe._("Rent Relief recalculated as 20% of annual rent (max N500,000)."),
			indicator="blue",
			alert=True,
		)
