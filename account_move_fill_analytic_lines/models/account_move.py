# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    analytic_account_id = fields.Many2one(comodel_name="account.analytic.account", string="Cuenta analítica", required=False)

    def set_analytic_account(self):
        if self.analytic_account_id and self.type == 'in_invoice':
            for l in self.invoice_line_ids:
                l.analytic_account_id = self.analytic_account_id.id
