import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

CABYS_URI = "https://api.hacienda.go.cr/fe/cabys"
QUERY = "*"
QUERY_MAX = 30000  # TODO Remove hardcoded
CABYS_INTERN_FROM_OFFICIAL = {
    "code": "codigo",
    "description": "descripcion",
    "tax_percentage": "impuesto",
}


class CAByS(models.Model):
    _name = "cabys"
    _description = "CAByS"

    name = fields.Char(
        compute="_compute_name",
        index=True,
        store=True,
    )
    code = fields.Char(
        index=True,
        required=True,
    )
    description = fields.Char(
        index=True,
        required=True,
    )
    tax_percentage = fields.Float()
    tax_id = fields.Many2one(
        comodel_name="account.tax",
        compute="_compute_tax_id",
        index=True,
        store=True,
    )

    @api.depends("code", "description")
    def _compute_name(self):
        for cabys in self:
            cabys.name = "{} - {}".format(cabys.code, cabys.description)

    @api.depends("tax_percentage")
    def _compute_tax_id(self):
        tax_obj = self.env["account.tax"]
        for cabys in self:
            cabys.tax_id = tax_obj.search(
                [
                    ("amount", "=", cabys.tax_percentage),
                    ("type_tax_use", "=", "sale"),
                    ("tax_code", "!=", False),
                ],
                limit=1,
            )

    def _download(self, query, query_max):
        r = requests.get(CABYS_URI, {"q": query, "top": query_max})
        if r.status_code != 200:
            raise ValidationError(_("Error downloading CAByS"))
        cabyss = r.json()["cabys"]
        cabyss_clean = [{k: r[v] for k, v in CABYS_INTERN_FROM_OFFICIAL.items()} for r in cabyss]
        return cabyss_clean

    @api.model
    def download_from_api(self, query=QUERY, query_max=QUERY_MAX):
        cabyss = self._download(query, query_max)
        self._update_cabys(cabyss)

    @api.model
    def _update_cabys(self, cabyss):
        to_create = []
        for cabys in cabyss:
            current_cabys = self.search([("code", "=", cabys["code"])], limit=1)
            if current_cabys:
                for k in CABYS_INTERN_FROM_OFFICIAL:
                    if getattr(current_cabys, k) != cabys[k]:
                        _logger.warning(
                            "CAByS Update {}.{} - {} -> {}".format(
                                current_cabys.code, k, getattr(current_cabys, k), cabys[k]
                            )
                        )
                        setattr(current_cabys, k, cabys[k])

            else:
                to_create.append(cabys)
        self.create(to_create)

    @api.model
    def update_tax_ids(self):
        cabyss = self.search([])
        for cabys in cabyss:
            cabys.tax_id = self.env["account.tax"].search(
                [
                    ("amount", "=", cabys.tax_percentage),
                    ("type_tax_use", "=", "sale"),
                    ("tax_code", "!=", ""),
                ],
                limit=1,
            )
