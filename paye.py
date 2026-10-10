"""Pure-Python PAYE calculator for the Nigeria Tax Act 2025 (effective 1 Jan 2026).

No Frappe imports here, so it can be unit-tested anywhere and reused by the
whitelisted API and the payroll reconciliation report.
"""

# (upper bound of band, rate). None = no upper bound.
NTA_2025_BANDS = [
	(800_000, 0.00),
	(3_000_000, 0.15),
	(12_000_000, 0.18),
	(25_000_000, 0.21),
	(50_000_000, 0.23),
	(None, 0.25),
]

RENT_RELIEF_RATE = 0.20
RENT_RELIEF_CAP = 500_000
PENSION_EMPLOYEE_RATE = 0.08  # of basic + housing + transport (PRA 2014)
NHF_RATE = 0.025  # of basic


def rent_relief(annual_rent, rate=RENT_RELIEF_RATE, cap=RENT_RELIEF_CAP):
	return round(min(max(annual_rent or 0, 0) * rate, cap), 2)


def tax_on_chargeable_income(chargeable, bands=NTA_2025_BANDS):
	"""Progressive tax on annual chargeable income. Returns (tax, breakdown)."""
	chargeable = max(chargeable or 0, 0)
	tax, lower, breakdown = 0.0, 0, []
	for upper, rate in bands:
		if chargeable <= lower:
			break
		top = chargeable if upper is None else min(chargeable, upper)
		portion = top - lower
		band_tax = portion * rate
		breakdown.append({"from": lower, "to": upper, "rate": rate, "taxable": portion, "tax": round(band_tax, 2)})
		tax += band_tax
		if upper is None:
			break
		lower = upper
	return round(tax, 2), breakdown


def compute_annual_paye(
	annual_gross,
	annual_basic=0,
	annual_housing=0,
	annual_transport=0,
	annual_rent=0,
	include_pension=True,
	include_nhf=True,
	other_reliefs=0,
):
	pension = (annual_basic + annual_housing + annual_transport) * PENSION_EMPLOYEE_RATE if include_pension else 0
	nhf = annual_basic * NHF_RATE if include_nhf else 0
	rr = rent_relief(annual_rent)
	chargeable = max(annual_gross - pension - nhf - rr - (other_reliefs or 0), 0)
	tax, breakdown = tax_on_chargeable_income(chargeable)
	return {
		"annual_gross": round(annual_gross, 2),
		"pension": round(pension, 2),
		"nhf": round(nhf, 2),
		"rent_relief": rr,
		"other_reliefs": round(other_reliefs or 0, 2),
		"chargeable_income": round(chargeable, 2),
		"annual_tax": tax,
		"monthly_tax": round(tax / 12, 2),
		"effective_rate": round(tax / annual_gross * 100, 2) if annual_gross else 0,
		"bands": breakdown,
	}
