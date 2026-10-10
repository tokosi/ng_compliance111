frappe.query_reports["Nigeria VAT Return"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.month_start(), -1), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.add_days(frappe.datetime.month_start(), -1), reqd: 1 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
