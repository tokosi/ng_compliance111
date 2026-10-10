"""Company profile (chart of accounts, payroll parameters, account map) shipped in ng_compliance/data."""

import json
import os
from functools import lru_cache

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


@lru_cache
def load(name="fedco"):
	with open(os.path.join(DATA_DIR, f"{name}_profile.json")) as f:
		return json.load(f)


@lru_cache
def load_chart(name="fedco"):
	with open(os.path.join(DATA_DIR, f"{name}_coa.json")) as f:
		return json.load(f)


def params(name="fedco"):
	return load(name)["payroll_parameters"]


def account_no(key, name="fedco"):
	return load(name)["accounts"][key]


def account_by_number(company, number):
	"""Leaf account for an account number in this company (None if missing)."""
	import frappe

	return frappe.db.get_value(
		"Account", {"company": company, "account_number": str(number), "is_group": 0}, "name"
	)


def account(company, key, name="fedco"):
	return account_by_number(company, account_no(key, name))
