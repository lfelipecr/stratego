from odoo import fields, models


class InvoiceLineElectronic(models.Model):
    _inherit = "account.move.line"

    tariff_head = fields.Char(
        string="Tariff heading for export invoice",
        required=False,
    )
