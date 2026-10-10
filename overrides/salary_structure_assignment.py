"""Keep Base in step with the Nigeria monthly pay fields on the Salary Structure Assignment.

* Any pay field filled  -> Base = Basic + COLA + Housing + Transport + Other allowances
* None filled, Base set -> everything is Basic (matches the FEDCO sample payslip)
"""

from frappe.utils import flt

PAY_FIELDS = ("ng_basic", "ng_cola", "ng_housing", "ng_transport", "ng_other_allowance")


def sync_base(doc, method=None):
	if not doc.meta.has_field("ng_basic"):
		return
	total = sum(flt(doc.get(f)) for f in PAY_FIELDS)
	if total:
		doc.base = total
	elif flt(doc.base):
		doc.ng_basic = flt(doc.base)
