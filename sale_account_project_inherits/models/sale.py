# -*- coding: utf-8 -*-
from odoo import api, models, fields
from odoo.tools.misc import formatLang


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    new_qty = fields.Float(string="Cantidad",  required=False)
    pax_days_hours = fields.Float(string="Por pax/días/horas",  required=False)
    new_subtotal = fields.Monetary(string="Subtotal", required=False)
    iva_tax_amount = fields.Float(string="IVA",  required=False)
    cost_iva_tax_amount = fields.Float(string="Costo + IVA",  required=False)
    fee_profit = fields.Float(string="FEE ganancia %",  required=False)
    amount_fee = fields.Float(string="Monto FEE",  required=False)
    supplier_id = fields.Many2one(string="Proveedor sugerido", comodel_name='res.partner', required=False)
    price_cost = fields.Monetary(string="Precio costo", required=False)
    supplier_tax_id = fields.Many2one(comodel_name='account.tax', string='Impuestos proveedor', domain=['|', ('active', '=', False), ('active', '=', True)])
    price_unit_backup = fields.Monetary(string="Respaldo de Precio", required=False)

    @api.onchange('new_qty', 'price_cost', 'price_unit', 'product_uom_qty', 'iva_tax_amount', 'new_subtotal', 'tax_id', 'supplier_tax_id', 'fee_profit', 'pax_days_hours')
    def onchange_new_qty_price_unit(self):
        self.product_uom_qty = self.new_qty * self.pax_days_hours
        self.new_subtotal = self.price_cost * self.product_uom_qty
        if self.supplier_tax_id:
            tax_amount = self.supplier_tax_id.amount
            self.iva_tax_amount = self.new_subtotal * (tax_amount / 100)
        self.cost_iva_tax_amount = self.new_subtotal + self.iva_tax_amount
        self.amount_fee = self.cost_iva_tax_amount * (self.fee_profit / 100)
        if self.product_uom_qty != 0:
            if self.product_id and self.product_id.standard_price == 0 and self.price_cost == 0:
                if self.price_unit == 0 and self.price_unit_backup != 0:
                    self.price_unit = self.price_unit_backup
                    # self.price_cost = 0
            else:
                self.price_unit = (self.cost_iva_tax_amount + self.amount_fee) / self.product_uom_qty

    @api.onchange('product_id')
    def product_uom_change(self):
        if self.order_id.pricelist_id and self.order_id.partner_id:
            product = self.product_id.with_context(
                lang=self.order_id.partner_id.lang,
                partner=self.order_id.partner_id,
                quantity=self.product_uom_qty,
                date=self.order_id.date_order,
                pricelist=self.order_id.pricelist_id.id,
                uom=self.product_uom.id,
                fiscal_position=self.env.context.get('fiscal_position')
            )
            if product:
                price = self.env['account.tax']._fix_tax_included_price_company(self._get_display_price(product), product.taxes_id, self.tax_id, self.company_id)
                date = self._context.get('date') or fields.Date.today()
                cur = product.currency_id
                if product.standard_price == 0:
                    self.price_unit = cur._convert(price, self.order_id.currency_id, self.env.company, date, round=False)
                    self.price_unit_backup = self.price_unit
                else:
                    self.price_cost = cur._convert(price, self.order_id.currency_id, self.env.company, date, round=False)
            else:
                self.price_cost = self.env['account.tax']._fix_tax_included_price_company(self._get_display_price(product), product.taxes_id, self.tax_id, self.company_id)
            self.fee_profit = self.product_id.fee_profit

    # @api.onchange('product_uom', 'product_uom_qty')
    # def product_uom_change(self):
    #     # if not self.product_uom or not self.product_id:
    #     #     self.price_cost = 0.0
    #     #     return
    #     if self.order_id.pricelist_id and self.order_id.partner_id and not self.price_cost:
    #         product = self.product_id.with_context(
    #             lang=self.order_id.partner_id.lang,
    #             partner=self.order_id.partner_id,
    #             quantity=self.product_uom_qty,
    #             date=self.order_id.date_order,
    #             pricelist=self.order_id.pricelist_id.id,
    #             uom=self.product_uom.id,
    #             fiscal_position=self.env.context.get('fiscal_position')
    #         )
    #         self.price_cost = self.env['account.tax']._fix_tax_included_price_company(self._get_display_price(product), product.taxes_id, self.tax_id, self.company_id)
    #     if self.product_id and not self.fee_profit:
    #         self.fee_profit = self.product_id.fee_profit

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id', 'supplier_tax_id', 'new_qty', 'iva_tax_amount', 'new_subtotal', 'fee_profit', 'pax_days_hours')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.product_uom_qty, product=line.product_id, partner=line.order_id.partner_shipping_id)
            line.update({
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded']
            })

    # @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    # def _compute_amount(self):
    #     """
    #     Compute the amounts of the SO line.
    #     """
    #     for line in self:
    #         price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
    #         taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.product_uom_qty, product=line.product_id, partner=line.order_id.partner_shipping_id)
    #         line.update({
    #             'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),#TODO POSIBLEMENTE CAMBIAR CALCULO DE IMPUESTO
    #             'price_total': taxes['total_included'],
    #             'price_subtotal': taxes['total_excluded'],
    #         })


    def _get_real_price_currency(self, product, rule_id, qty, uom, pricelist_id):
        """Retrieve the price before applying the pricelist
            :param obj product: object of current product record
            :parem float qty: total quentity of product
            :param tuple price_and_rule: tuple(price, suitable_rule) coming from pricelist computation
            :param obj uom: unit of measure of current order line
            :param integer pricelist_id: pricelist id of sales order"""
        PricelistItem = self.env['product.pricelist.item']
        field_name = 'lst_price'
        currency_id = None
        product_currency = None
        if rule_id:
            pricelist_item = PricelistItem.browse(rule_id)
            if pricelist_item.pricelist_id.discount_policy == 'without_discount':
                while pricelist_item.base == 'pricelist' and pricelist_item.base_pricelist_id and pricelist_item.base_pricelist_id.discount_policy == 'without_discount':
                    price, rule_id = pricelist_item.base_pricelist_id.with_context(uom=uom.id).get_product_price_rule(product, qty, self.order_id.partner_id)
                    pricelist_item = PricelistItem.browse(rule_id)

            if pricelist_item.base == 'standard_price':
                field_name = 'standard_price'
            if pricelist_item.base == 'pricelist' and pricelist_item.base_pricelist_id:
                field_name = 'price'
                product = product.with_context(pricelist=pricelist_item.base_pricelist_id.id)
                product_currency = pricelist_item.base_pricelist_id.currency_id
            currency_id = pricelist_item.pricelist_id.currency_id

        product_currency = product_currency or(product.company_id and product.company_id.currency_id) or self.env.company.currency_id
        if not currency_id:
            currency_id = product_currency
            cur_factor = 1.0
        else:
            if currency_id.id == product_currency.id:
                cur_factor = 1.0
            else:
                cur_factor = currency_id._get_conversion_rate(product_currency, currency_id, self.company_id or self.env.company, self.order_id.date_order or fields.Date.today())

        product_uom = self.env.context.get('uom') or product.uom_id.id
        if uom and uom.id != product_uom:
            # the unit price is in a different uom
            uom_factor = uom._compute_price(1.0, product.uom_id)
        else:
            uom_factor = 1.0
        if product['standard_price'] == 0:
            product_price = product['standard_price']
        else:
            product_price = product['list_price']
        return product_price * uom_factor * cur_factor, currency_id
    
    def _get_display_price(self, product):
        # TO DO: move me in master/saas-16 on sale.order
        # awa: don't know if it's still the case since we need the "product_no_variant_attribute_value_ids" field now
        # to be able to compute the full price

        # it is possible that a no_variant attribute is still in a variant if
        # the type of the attribute has been changed after creation.
        no_variant_attributes_price_extra = [
            ptav.price_extra for ptav in self.product_no_variant_attribute_value_ids.filtered(
                lambda ptav:
                    ptav.price_extra and
                    ptav not in product.product_template_attribute_value_ids
            )
        ]
        if no_variant_attributes_price_extra:
            product = product.with_context(
                no_variant_attributes_price_extra=tuple(no_variant_attributes_price_extra)
            )

        if self.order_id.pricelist_id.discount_policy == 'with_discount':
            price = product.with_context(pricelist=self.order_id.pricelist_id.id).standard_price
            if price == 0:
                price = product.with_context(pricelist=self.order_id.pricelist_id.id).list_price
            return price
        product_context = dict(self.env.context, partner_id=self.order_id.partner_id.id, date=self.order_id.date_order, uom=self.product_uom.id)

        final_price, rule_id = self.order_id.pricelist_id.with_context(product_context).get_product_price_rule(self.product_id, self.product_uom_qty or 1.0, self.order_id.partner_id)
        base_price, currency = self.with_context(product_context)._get_real_price_currency(product, rule_id, self.product_uom_qty, self.product_uom, self.order_id.pricelist_id.id)
        if currency != self.order_id.pricelist_id.currency_id:
            base_price = currency._convert(
                base_price, self.order_id.pricelist_id.currency_id,
                self.order_id.company_id or self.env.company, self.order_id.date_order or fields.Date.today())
        # negative discounts (= surcharge) are included in the display price
        return max(base_price, final_price)

    def _timesheet_create_project_prepare_values(self):
        res = super(SaleOrderLine, self)._timesheet_create_project_prepare_values()
        res.update({'name': self.order_id.x_studio_nombre_proyecto})
        return res
    

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    amount_discount = fields.Monetary(string="Descuento", compute='_compute_amount_discount',required=False)
    new_subtotal = fields.Monetary(string="Subtotal", compute='_amount_all', required=False)

    @api.depends('amount_undiscounted')
    def _compute_amount_discount(self):
        for order in self:
            order.update({'amount_discount': order.amount_undiscounted - order.amount_untaxed})

    def group_by_section(self, lines):
        res = []
        for l in lines:
            append = False
            if l.display_type in ('line_section', 'line_note'):
                continue
            if res:
                for r in res:
                    if not append:
                        if not self.find_product(res, l.product_id.section_id, l.name,l.price_subtotal):
                            res.append({'qty': l.product_uom_qty, 'description': l.name, 'amount': formatLang(self.env, l.price_subtotal, currency_obj=l.currency_id),'section_id': l.product_id.section_id.id})
                            append = True
                        else:
                            break
            else:
                if l.product_id.section_id.id:
                    res.append({'qty': l.product_uom_qty, 'description': l.product_id.section_id.name + ": " + l.name, 'amount': formatLang(self.env, l.price_subtotal, currency_obj=l.currency_id),'section_id': l.product_id.section_id.id})
                else:
                    res.append({'qty': l.product_uom_qty, 'description': l.name,'amount': formatLang(self.env, l.price_subtotal, currency_obj=l.currency_id), 'section_id': l.product_id.section_id.id})

        return res

    def find_product(self, res, section, description, subtotal):
        find = False
        for r in res:
            if section:
                if section.id in r.values() and not find:
                    r['qty'] = 1
                    if section.name in r['description']:
                        r['description'] += " ," + description
                    else:
                        r['description'] += section.name + ": " + description
                    r['amount'] += round(subtotal, 2)
                    find = True
        return find

    def compute_crc_amount(self, amount, currency):
        usd = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        if currency == 'CRC':
            res_currency = usd
            rate = 1 / res_currency.rate
            res_amount = amount / rate
        else:
            res_currency = self.env['res.currency'].search([('name', '=', 'CRC')], limit=1)
            rate = 1 / usd.rate
            res_amount = amount * rate
        return formatLang(self.env, res_amount, currency_obj=res_currency)

    @api.depends('order_line.price_total')
    def _amount_all(self):
        """
        Compute the total amounts of the SO.
        """
        for order in self:
            amount_untaxed = amount_tax = 0.0
            for line in order.order_line:
                amount_untaxed += line.price_subtotal
                amount_tax += line.price_tax
            order.update({
                'new_subtotal': amount_untaxed + order.amount_discount,
                'amount_untaxed': amount_untaxed,
                'amount_tax': amount_tax,
                'amount_total': amount_untaxed + amount_tax,
            })

    def _prepare_analytic_account_data(self, prefix=None):
        res = super(SaleOrder, self)._prepare_analytic_account_data(prefix=prefix)
        res.update({'name': self.x_studio_nombre_proyecto})
        return res
