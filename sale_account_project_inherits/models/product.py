# -*- coding: utf-8 -*-
from odoo import api, models, fields


class ProductSection(models.Model):
    _name = 'product.section'

    name = fields.Char(string="Nombre", required=True)


class ProductProduct(models.Model):
    _inherit = 'product.template'

    section_id = fields.Many2one(comodel_name="product.section", string="Sección", required=False)
    fee_profit = fields.Float(string="FEE ganancia %", required=False)

