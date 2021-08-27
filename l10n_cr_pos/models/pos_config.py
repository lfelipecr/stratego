# -*- coding: utf-8 -*-
from odoo import api, fields, models

TYPES = {
    0 : u'FE-Secuencia de Factura electrónica',
    1 : u'NC-Secuencia de Nota de crédito electrónica',
    2 : u'TE-Secuencia de Tiquete electrónico',
}

class PosConfig(models.Model):
    _inherit = "pos.config"

    sucursal = fields.Integer(string="Sucursal",required=False,default="1")
    terminal = fields.Integer(string="Terminal",required=False,default="1")
    sequence_fe_id = fields.Many2one(comodel_name="ir.sequence",string=u"Secuencia Factura Electrónica",required=False)
    sequence_nc_id = fields.Many2one(oldname="return_sequence_id",comodel_name="ir.sequence",string=u"Secuencia Notas de Crédito Electrónica",required=False)
    sequence_te_id = fields.Many2one(comodel_name="ir.sequence",string=u"Secuencia Tiquete Electrónico",required=False,)

    _sql_constraints = [
        ('sucursal_company_uniq', 'unique (sucursal, terminal, company_id)',
         u'La sucursal debe ser única por compañia!'),
    ]

    @api.model
    def set_sequences(self):
        for record in self.search([]):
            record.sequence_fe_id = self.env["ir.sequence"].search([("code", "=", "sequece.FE")], limit=1)[0]
            record.sequence_te_id = self.env["ir.sequence"].search([("code", "=", "sequece.TE")], limit=1)[0]
            record.sequence_nc_id = self.env["ir.sequence"].search([("code", "=", "sequece.NC")], limit=1)[0]


    def create_sequences(self):
        """
            <field name="name">Secuencia de Factura Electrónica</field>
            <field name="code">sequece.FE</field>
            <field name="prefix"/>
            <field name="implementation">no_gap</field>
            <field name="padding">10</field>
        :return:
        """
        list  = []
        model_sequence = self.env['ir.sequence']
        for i in range(0,3):
            type = TYPES[i].split('-')

            data = {
                'name': 'Sucursal|' + str(self.sucursal) + '|' + type[1],
                'code': 'sequence.sucursal.'+str(str(self.sucursal))+'.'+type[0],
                'implementation': 'no_gap',
                'padding': 10
            }
            list.append(data)

        r = model_sequence.create(list)
        self.sequence_fe_id = r.filtered(lambda fe: fe.code.split('.')[3]=='FE').id
        self.sequence_nc_id = r.filtered(lambda nc: nc.code.split('.')[3]=='NC').id
        self.sequence_te_id = r.filtered(lambda te: te.code.split('.')[3]=='TE').id



