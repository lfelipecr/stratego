from odoo import fields, models


class AccountConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    adjustment_credit_account_id = fields.Many2one(
        related="company_id.adjustment_credit_account_id",
    )
    adjustment_debit_account_id = fields.Many2one(
        related="company_id.adjustment_debit_account_id",
    )
    invoice_import_email = fields.Char(
        related="company_id.invoice_import_email",
    )
