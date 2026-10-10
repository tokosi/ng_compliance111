"""Fill the Employee's Tax Office from the PAYE state when left blank."""

TAX_OFFICES = {
	"Lagos": "LIRS",
	"Ondo": "ODIRS",
	"FCT Abuja": "FCT-IRS",
	"Ogun": "OGIRS",
	"Oyo": "OYSIRS",
	"Ekiti": "EKIRS",
	"Edo": "EIRS",
	"Rivers": "RIRS",
	"Kano": "KIRS",
	"Kaduna": "KADIRS",
	"Kwara": "KW-IRS",
	"Enugu": "ESIRS",
	"Anambra": "AIRS",
}


def tax_office_for(state):
	if not state:
		return None
	return TAX_OFFICES.get(state) or f"{state} State IRS"


def set_tax_office(doc, method=None):
	if doc.get("ng_paye_state") and not doc.get("ng_tax_office"):
		doc.ng_tax_office = tax_office_for(doc.ng_paye_state)
