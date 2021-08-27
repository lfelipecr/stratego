from odoo import _, fields, models


class PartnerElectronic(models.Model):
    _inherit = "res.partner"

    commercial_name = fields.Char()
    identification_id = fields.Many2one(
        comodel_name="identification.type",
        string="ID Type",
    )
    payment_methods_id = fields.Many2one(
        comodel_name="payment.methods",
    )
    has_exoneration = fields.Boolean()
    type_exoneration = fields.Many2one(
        comodel_name="aut.ex",
    )
    exoneration_number = fields.Char()
    institution_name = fields.Char(
        string="Issuing Institution",
    )
    date_issue = fields.Date()
    date_expiration = fields.Date()
    _sql_constraints = [
        (
            "vat_unique",
            "UNIQUE(vat)",
            _("No pueden existir dos clientes/proveedores con el mismo número de identificación"),
        )
    ]
