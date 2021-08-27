from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    adjustment_credit_account_id = fields.Many2one(
        comodel_name="account.account",
        domain=[
            ("deprecated", "=", False),
        ],
    )
    adjustment_debit_account_id = fields.Many2one(
        comodel_name="account.account",
        domain=[
            ("deprecated", "=", False),
        ],
    )
    invoice_import_email = fields.Char(
        string="Mail Gateway: Destination E-mail",
        help="This field is used in multi-company setups to import the invoices received by the mail gateway in the appropriate company",
    )
    _sql_constraints = [
        (
            "invoice_import_email_uniq",
            "unique(invoice_import_email)",
            "This invoice import email already exists!",
        ),
    ]
