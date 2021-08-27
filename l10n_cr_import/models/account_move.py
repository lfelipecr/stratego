import base64
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_re, email_split

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    state_email = fields.Selection(
        selection=[
            ("no_email", _("No email account")),
            ("sent", _("Sent")),
            ("fe_error", _("Error FE")),
        ],
        copy=False,
    )

    def name_get(self):
        """
        - Add amount_untaxed in name_get of invoices
        - Skipp number usage on invoice from incoming mail
        """
        if self._context.get("invoice_from_incoming_mail"):
            logging.info("Factura de correo")
            res = []
            for inv in self:
                res.append((inv.id, (inv.name or str(inv.id)) + "MI"))
            return res
        res = super(AccountMove, self).name_get()
        if self._context.get("invoice_show_amount"):
            new_res = []
            for (inv_id, name) in res:
                inv = self.browse(inv_id)
                name += _(" Amount w/o tax: {} {}").format(inv.amount_untaxed, inv.currency_id.name)
                new_res.append((inv_id, name))
            return new_res
        else:
            return res

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        logging.info("-------- Entra a msg_new --------")
        # OVERRIDE
        # Add custom behavior when receiving a new invoice through the mail's gateway.
        if (custom_values or {}).get("move_type", "entry") not in ("out_invoice", "in_invoice"):
            return super().message_new(msg_dict, custom_values=custom_values)

        def is_internal_partner(partner):
            # Helper to know if the partner is an internal one.
            return partner.user_ids and all(
                user.has_group("base.group_user") for user in partner.user_ids
            )

        # Search for partners in copy.
        cc_mail_addresses = email_split(msg_dict.get("cc", ""))
        followers = [
            partner for partner in self._mail_find_partner_from_emails(cc_mail_addresses) if partner
        ]
        logging.info("-------- followers --------")

        # Search for partner that sent the mail.
        from_mail_addresses = email_split(msg_dict.get("from", ""))
        senders = partners = [
            partner
            for partner in self._mail_find_partner_from_emails(from_mail_addresses)
            if partner
        ]
        logging.info("-------- senders --------")

        # Search for partners using the user.
        if not senders:
            senders = partners = list(self._mail_search_on_user(from_mail_addresses))

        if partners:
            # Check we are not in the case when an internal user forwarded the mail manually.
            if is_internal_partner(partners[0]):
                # Search for partners in the mail's body.
                body_mail_addresses = set(email_re.findall(msg_dict.get("body")))
                partners = [
                    partner
                    for partner in self._mail_find_partner_from_emails(body_mail_addresses)
                    if not is_internal_partner(partner)
                ]
        logging.info("-------- partners --------")

        # Little hack: Inject the mail's subject in the body.
        if msg_dict.get("subject") and msg_dict.get("body"):
            msg_dict["body"] = "<div><div><h3>{}</h3></div>{}</div>".format(
                msg_dict["subject"],
                msg_dict["body"],
            )

        # Create the invoice.
        values = {
            "name": "Invoice from email",  # we have to give the name otherwise it will be set to the mail's subject
            "invoice_source_email": from_mail_addresses[0],
            "partner_id": partners and partners[0].id or False,
        }
        if custom_values.get("journal_id"):
            journal = custom_values.get("journal_id")
        else:
            journal = self.env["account.journal"].search([("type", "=", "purchase")], limit=1)
        move_ctx = self.with_context(
            default_move_type="in_invoice",
            default_journal_id=journal.id,
        )
        logging.info("-------- valores y contexto --------")
        move = super(AccountMove, move_ctx).message_new(msg_dict, custom_values=values)
        move._compute_name()  # because the name is given, we need to recompute in case it is the first invoice of the journal
        logging.info("-------- Crea factura --------")

        # Assign followers.
        all_followers_ids = {
            partner.id for partner in followers + senders + partners if is_internal_partner(partner)
        }
        move.message_subscribe(list(all_followers_ids))
        logging.info("-------- asigna seguidores --------")
        return move

    def load_xml_data(self):
        if (
            self.move_type == "out_invoice" or self.move_type == "out_refund"
        ) and self.xml_comprobante:
            # TODO why is this here?
            self.electronic_sequence = re.sub(r"[^\d]+", "", self.electronic_sequence)
            root = ET.fromstring(  # TODO why is this here?
                re.sub(
                    ' xmlns="[^"]+"',
                    "",
                    base64.b64decode(self.xml_comprobante).decode("utf-8"),
                    count=1,
                )
            )

            partner_vat = root.findall("Receptor")[0].find("Identificacion")[1].text
            date_issuance = root.findall("FechaEmision")[0].text
            sequence = root.findall("NumeroConsecutivo")[0].text

            partner = self.env["res.partner"].search([("vat", "=", partner_vat)])

            if partner and self.partner_id.id != partner.id:
                raise UserError(
                    _(
                        "The customer with identification {} does not match the customer of this invoice: {}"
                    ).format(partner, self.partner_id.vat)
                )
            elif str(self.invoice_date) != date_issuance:
                raise UserError(
                    _("The date of the XML {} does not match the date of this invoice").format(
                        date_issuance
                    )
                )
            elif self.electronic_sequence != sequence:
                raise UserError(
                    _("The consecutive number {} does not match the one on this invoice").format(
                        sequence
                    )
                )
            else:
                self.number_electronic = root.findall("Clave")[0].text
                self.date_issuance = date_issuance
                self.invoice_date = date_issuance

            currency_name = root.find("ResumenFactura").find("CodigoMoneda").text
            self.currency_id = (
                self.env["res.currency"].search([("name", "=", currency_name)], limit=1).id
            )

        elif self.xml_supplier_approval:
            xml_string = re.sub(
                ' xmlns="[^"]+"',
                "",
                base64.b64decode(self.xml_supplier_approval).decode("utf-8"),
                count=1,
            ).encode("utf-8")
            root = ET.fromstring(xml_string)

            xml_decoded = base64.b64decode(self.xml_supplier_approval)

            try:
                factura = etree.fromstring(xml_decoded)
            except Exception as e:
                _logger.error("MAB - This XML file is not XML-compliant. Exception {}".format(e))
                return {"status": 400, "text": "Excepción de conversión de XML"}

            pretty_xml_string = etree.tostring(
                factura, pretty_print=True, encoding="UTF-8", xml_declaration=True
            )

            _logger.info("Send_file XML: {}".format(pretty_xml_string))

            namespaces = factura.nsmap
            inv_xmlns = namespaces.pop(None)
            namespaces["inv"] = inv_xmlns

            self.consecutive_number_receiver = factura.xpath(
                "inv:NumeroConsecutivo", namespaces=namespaces
            )[0].text

            self.payment_reference = self.consecutive_number_receiver
            self.number_electronic = factura.xpath("inv:Clave", namespaces=namespaces)[0].text
            self.date_issuance = factura.xpath("inv:FechaEmision", namespaces=namespaces)[0].text
            if "." in self.date_issuance:  # Time with milliseconds
                self.date_issuance = self.date_issuance[
                    : self.date_issuance.find(".") + 7
                ]  # Truncate first 6 digits of seconds
            date_formats = [
                "%Y-%m-%dT%H:%M:%S-06:00",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
            ]
            for date_format in date_formats:
                try:
                    date_time_obj = datetime.strptime(self.date_issuance, date_format)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(_("No valid date format for {}").format(self.date_issuance))
            invoice_date = date_time_obj.date()

            self.invoice_date = invoice_date

            try:
                emisor = factura.xpath(
                    "inv:Emisor/inv:Identificacion/inv:Numero", namespaces=namespaces
                )[0].text
            except IndexError:
                raise UserError(
                    _("The issuer has no identification number, the xml received is invalid")
                )

            try:
                receptor = factura.xpath(
                    "inv:Receptor/inv:Identificacion/inv:Numero", namespaces=namespaces
                )[0].text
            except IndexError:
                raise UserError(
                    _("The receiver has no identification number, the xml received is invalid")
                )

            currency_node = factura.xpath(
                "inv:ResumenFactura/inv:CodigoTipoMoneda/inv:CodigoMoneda",
                namespaces=namespaces,
            )
            if currency_node:
                self.currency_id = (
                    self.env["res.currency"]
                    .search([("name", "=", currency_node[0].text)], limit=1)
                    .id
                )
            else:
                self.currency_id = (
                    self.env["res.currency"]
                    .search([("name", "=", "CRC")], limit=1)
                    .id  # TODO use base currency
                )

            if receptor != self.company_id.vat:
                raise UserError(
                    _(
                        "The receiver does not correspond to the current company with identification {}. Please activate the correct company."
                    ).format(receptor)
                )
            partner = self.env["res.partner"].search(
                [
                    ("vat", "=", emisor),
                    ("supplier_rank", ">", 0),
                    "|",
                    ("company_id", "=", self.company_id.id),
                    ("company_id", "=", False),
                ],
                limit=1,
            )
            if partner:
                self.partner_id = partner.id
            else:
                raise UserError(
                    _(
                        "The provider with id {} does not exist. Please create it in the system first."
                    ).format(emisor)
                )

            tax_node = factura.xpath("inv:ResumenFactura/inv:TotalImpuesto", namespaces=namespaces)
            if tax_node:
                self.amount_tax_electronic_invoice = tax_node[0].text

            self.amount_total_electronic_invoice = factura.xpath(
                "inv:ResumenFactura/inv:TotalComprobante", namespaces=namespaces
            )[0].text
            load_lines = bool(self.env["ir.config_parameter"].sudo().get_param("load_lines"))
            if not load_lines:
                return
            lines = root.find("DetalleServicio").findall("LineaDetalle")
            new_lines = self.env["account.move.line"]
            for line in lines:
                product_uom = (
                    self.env["uom.uom"]
                    .search([("code", "=", line.find("UnidadMedida").text)], limit=1)
                    .id
                )
                total_amount = float(line.find("MontoTotal").text)
                discount_percentage = 0.0
                discount_note = None
                discount_node = line.find("Descuento")
                if discount_node:
                    discount_amount_node = discount_node.find("MontoDescuento")
                    discount_amount = float(discount_amount_node.text or "0.0")
                    discount_percentage = discount_amount / total_amount * 100
                    discount_note = discount_node.find("NaturalezaDescuento").text
                else:
                    discount_amount_node = line.find("MontoDescuento")
                    if discount_amount_node:
                        discount_amount = float(discount_amount_node.text or "0.0")
                        discount_percentage = discount_amount / total_amount * 100
                        discount_note = line.find("NaturalezaDescuento").text

                taxes = self.env["account.tax"]
                tax_nodes = line.findall("Impuesto")
                total_tax = 0.0
                if tax_nodes:
                    for tax_node in tax_nodes:
                        if tax_node:
                            tax_amount = float(tax_node.find("Monto").text)
                            if tax_amount > 0:
                                tax_code = re.sub(r"[^0-9]+", "", tax_node.find("Codigo").text)
                                tax = self.env["account.tax"].search(
                                    [
                                        ("tax_code", "=", tax_code),
                                        ("amount", "=", tax_node.find("Tarifa").text),
                                        ("type_tax_use", "=", "purchase"),
                                    ],
                                    limit=1,
                                )
                                if tax:
                                    taxes += tax
                                    total_tax += tax_amount
                                else:
                                    raise UserError(
                                        _(
                                            "A tax type in the XML does not exist in the configuration: {}"
                                        ).format(tax_node.find("Codigo").text)
                                    )

                default_account_id = (
                    self.env["ir.config_parameter"].sudo().sudo().get_param("expense_account_id")
                )
                invoice_line = self.env["account.move.line"].new(
                    {
                        "name": line.find("Detalle").text,
                        "move_id": self.id,
                        "price_unit": line.find("PrecioUnitario").text,
                        "quantity": line.find("Cantidad").text,
                        "uom_id": product_uom,
                        "sequence": line.find("NumeroLinea").text,
                        "discount": discount_percentage,
                        "discount_note": discount_note,
                        "total_amount": total_amount,
                        "amount_untaxed": float(line.find("SubTotal").text),
                        "tax_ids": taxes,
                        "total_tax": total_tax,
                        "account_id": default_account_id,
                    }
                )
                new_lines += invoice_line
            self.invoice_line_ids = new_lines
            tax_node = factura.xpath("inv:ResumenFactura/inv:TotalImpuesto", namespaces=namespaces)
            if tax_node:
                self.amount_tax_electronic_invoice = tax_node[0].text
            self.amount_total_electronic_invoice = factura.xpath(
                "inv:ResumenFactura/inv:TotalComprobante", namespaces=namespaces
            )[0].text
            # TODO: Verificar si es necesario recalcular los impuestos
            #  self.compute_taxes()
