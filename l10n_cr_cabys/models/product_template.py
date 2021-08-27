from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    cabys_id = fields.Many2one(
        string="CAByS",
        comodel_name="cabys",
        ondelete="restrict",
    )
    taxes_id = fields.Many2many(  # Overwrite base
        compute="_compute_tax_from_cabys",
        store=True,
    )

    @api.depends("cabys_id")
    def _compute_tax_from_cabys(self):  # TODO the change doesn't occur in real time in the frontend
        for template in self:
            if not template.cabys_id:
                continue
            template.taxes_id = [(6, None, [template.cabys_id.tax_id.id])]
