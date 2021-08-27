import base64
import logging

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .. import cr_edi

_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = "account.move"

    number_electronic = fields.Char(
        copy=False,
        index=True,
        readonly=True,
    )
    date_issuance = fields.Char(
        copy=False,
        readonly=True,
    )
    consecutive_number_receiver = fields.Char(
        copy=False,
        readonly=True,
        index=True,
    )
    state_send_invoice = fields.Selection(
        selection=[
            ("aceptado", _("Accepted")),
            ("rechazado", _("Rejected")),
            ("error", "Error"),
            ("na", _("Not Apply")),
            ("ne", _("Not Found")),
            ("firma_invalida", _("Invalid Signature")),
            ("procesando", _("Processing")),
        ],
        readonly=True,
    )
    state_tributacion = fields.Selection(
        selection=[
            ("aceptado", _("Accepted")),
            ("rechazado", _("Rejected")),
            ("recibido", _("Received")),
            ("firma_invalida", _("Invalid Signature")),
            ("error", "Error"),
            ("procesando", _("Processing")),
            ("na", _("Not Aplly")),
            ("ne", _("Not Found")),
        ],
        copy=False,
        readonly=True,
    )
    state_invoice_partner = fields.Selection(
        selection=[
            ("1", _("Accepted")),
            ("3", _("Rejected")),
            ("2", _("Partial Acceptance")),
        ],
    )
    xml_respuesta_tributacion = fields.Binary(
        copy=False,
        readonly=True,
    )
    electronic_invoice_return_message = fields.Text(
        copy=False,
        readonly=True,
    )
    fname_xml_respuesta_tributacion = fields.Char(
        copy=False,
    )
    xml_comprobante = fields.Binary(
        copy=False,
    )
    fname_xml_comprobante = fields.Char(
        copy=False,
    )
    xml_supplier_approval = fields.Binary(
        copy=False,
    )
    fname_xml_supplier_approval = fields.Char(
        copy=False,
    )
    amount_tax_electronic_invoice = fields.Monetary(
        readonly=True,
    )
    amount_total_electronic_invoice = fields.Monetary(
        readonly=True,
    )
    electronic_sequence = fields.Char(
        readonly=True,
        copy=False,
    )
    ignore_total_difference = fields.Boolean()
    to_process = fields.Boolean(
        compute="_compute_to_process",
    )

    @api.depends("company_id.frm_ws_ambiente", "journal_id.to_process")
    def _compute_to_process(self):
        for invoice in self:
            invoice.to_process = (
                invoice.company_id.frm_ws_ambiente and invoice.journal_id.to_process
            )

    # invoice_payment_term_id = fields.Many2one(required=True)

    _sql_constraints = [
        (
            "number_electronic_uniq",
            "UNIQUE(company_id, number_electronic)",
            "La clave de comprobante debe ser única",
        ),
    ]

    def get_amounts(self):
        """Compute amounts to be used in XML generation based on invoice lines
        The amounts are:
        `service_taxed`: Sum line.no_discount_amount
        `service_no_taxed`: Sum line.no_discount_amount
        `service_exempt`: TODO
        `product_taxed`: Sum line.no_discount_amount
        `product_no_taxed`: Sum line.no_discount_amount
        `product_exempt`: TODO
        `discount`: Sum line.discount_amount
        `other_charges`: TODO
        Returns:
            dict: Amounts calculated
        """
        self.ensure_one()
        amounts = {
            "service_taxed": 0,
            "service_no_taxed": 0,
            "service_exempt": 0,  # TODO
            "product_taxed": 0,
            "product_no_taxed": 0,
            "product_exempt": 0,  # TODO
            "discount": 0,
            "other_charges": 0,  # TODO
        }
        for line in self.invoice_line_ids:
            if line.display_type:  # Section or note
                continue
            if False:  # TODO other charges
                continue
            amounts["discount"] += line.discount_amount
            line_type = "service" if line.product_id.type == "service" else "product"
            is_tax = "taxed" if line.tax_ids else "no_taxed"
            amounts[line_type + "_" + is_tax] += line.no_discount_amount  # TODO Exempt
        return amounts

    @api.constrains("xml_supplier_approval")
    def _verify_xml_supplier_approval(self):
        """Verify XML structure and data
        Raises:
            UserError: If no valid XML structure
            ValidationError: If misssing required data
        """
        for invoice in self:
            if not invoice.xml_supplier_approval:
                continue
            xml_decoded = base64.b64decode(invoice.xml_supplier_approval)
            try:
                root = etree.fromstring(xml_decoded)
            except etree.XMLSyntaxError as e:
                raise UserError(_("No valid XML structure: {}").format(e))

            nsmap = root.nsmap
            inv_xmlns = nsmap.pop(None)
            nsmap["inv"] = inv_xmlns

            nodes_to_check = (
                "inv:Clave",
                "inv:FechaEmision",
                "inv:Emisor/inv:Identificacion/inv:Numero",
                "inv:Receptor/inv:Identificacion/inv:Numero",
                "inv:ResumenFactura/inv:TotalComprobante",
            )
            error = ""
            for node in nodes_to_check:
                if not root.xpath(node, namespaces=nsmap):
                    error += _("The XML fiel does not contain the node: {}\n").format(node)
            if error:
                raise ValidationError(
                    _("{}\nPlease upload a file with the correct format.").format(error)
                )

    def update_state(self):
        """Check document status in the API, and if is valid set the state_tributacion or state_send_invoice (type depends) and the date_issuance to CR actual time

        Raises:
            ValidationError: If the response is not expected
            ValidationError: If the document type is not expected
        """
        self.ensure_one()

        response_json = cr_edi.api.query_document(
            clave=self.number_electronic,
            token=self.company_id.get_token(),
            client_id=self.company_id.frm_ws_ambiente,
        )
        state = response_json.get("ind-estado")

        if self.move_type in ("out_invoice", "out_refund"):
            self.state_tributacion = state
            self.date_issuance = cr_edi.utils.get_time_cr()
        elif self.move_type in ("in_invoice", "in_refund"):
            self.state_send_invoice = state

        self.fname_xml_respuesta_tributacion = "respuesta_{}.xml".format(self.number_electronic)
        self.xml_respuesta_tributacion = response_json.get("respuesta-xml")
        # self._send_mail()

    def send_mrs_to_hacienda(self):
        """Send message to API"""
        for invoice in self.filtered("to_process"):
            if (
                not invoice.xml_supplier_approval
                or not invoice.state_invoice_partner
                or invoice._has_error()
            ):
                continue

            if invoice.state_send_invoice == "procesando":
                invoice.update_state()
                continue

            message_body = _("<p><b>Sending Receiver Message</b></p>")
            if invoice.state_send_invoice == "rechazado" or invoice.state_send_invoice == "error":
                message_body += (
                    "<p><b>Consecutive Changing of Receiver Message</b> <br />"
                    "<b>Previous consecutive:</b> {} <br/>"
                    "<b>Previous state:</b> {} </p>".format(
                        invoice.consecutive_number_receiver,
                        invoice.state_send_invoice,
                    )
                )
            message = invoice.set_electronic_invoice_data()
            invoice.send_message(message_body, message)

    def set_electronic_invoice_data(self):
        """Set consecutive_number_receiver, tipo_document, fname_xml_comprobante and xml_comprobante fields

        Returns:
            str: State Invoice Partner string
        """
        state_invoice_partner_datas = self._get_state_invoice_partner_datas()

        self.consecutive_number_receiver = cr_edi.utils.compute_full_sequence(
            branch=self.company_id.sucursal_MR,
            terminal=self.company_id.terminal_MR,
            doc_type=state_invoice_partner_datas["document_type"],
            sequence=state_invoice_partner_datas["sequence"].next_by_id(),
        )

        self.tipo_documento = state_invoice_partner_datas["document_type"]
        self.fname_xml_comprobante = "{}_{}.xml".format(self.tipo_documento, self.number_electronic)

        xml = cr_edi.gen_xml.mensaje_receptor(
            electronic_number=self.number_electronic,
            issuer_vat=self.partner_id.vat,
            emition_date=self.date_issuance,
            message_type=self.state_invoice_partner,
            message=state_invoice_partner_datas["message"],
            receiver_vat=self.company_id.vat,
            receiver_sequence=self.consecutive_number_receiver,
            amount_tax=self.amount_tax_electronic_invoice,
            amount_total=self.amount_total_electronic_invoice,
            activity_code=self.activity_id.code,
            tax_status="01",  # TODO check
        )
        xml_signed = cr_edi.utils.sign_xml(
            cert=self.company_id.signature,
            pin=self.company_id.frm_pin,
            xml=xml,
        )
        self.xml_comprobante = base64.encodebytes(xml_signed)
        return state_invoice_partner_datas["message"]

    def send_message(self, message_body, message):
        """Send message to api

        Args:
            message_body (str): Message body to be posted in document
            message ([str]): Message type
        """
        token = self.company_id.get_token()
        response_json = cr_edi.api.send_message(
            inv=self,
            date_cr=cr_edi.utils.get_time_cr(),
            xml=base64.b64decode(self.xml_comprobante),
            token=token,
            client_id=self.company_id.frm_ws_ambiente,
        )
        status = response_json.get("status")
        if 200 <= status <= 299:
            self.state_send_invoice = "procesando"
            self.retry(token, message_body, message)
        else:
            self.state_send_invoice = "error"
            _logger.error(
                "E-INV CR - Invoice: {}  Error sending Acceptance Message: {}".format(
                    self.number_electronic, response_json.get("text")
                )
            )

    def _get_state_invoice_partner_datas(self):  # TODO set this attributes in a new model
        """Get message, document type and sequence from State Invoice partner

        Returns:
            dict: Datas
        """
        state_invoice_partner_to_datas = {
            "1": {
                "message": _("Accepted"),
                "document_type": "CCE",
                "sequence": self.company_id.CCE_sequence_id,
            },
            "2": {
                "message": _("Partial accepted"),
                "document_type": "CPCE",
                "sequence": self.company_id.CPCE_sequence_id,
            },
            "3": {
                "message": _("Rejected"),
                "document_type": "RCE",
                "sequence": self.company_id.RCE_sequence_id,
            },
        }
        return state_invoice_partner_to_datas[self.state_invoice_partner]

    def _has_error(self):
        """Check if the invoices has errors to be processed in the send_mrs_to_hacienda functions

        Raises:
            UserError: If state unexpected

        Returns:
            str: Error string
        """
        if self.state_send_invoice in ("aceptado", "rechazado", "na"):  # TODO why
            raise UserError(_("The invoice has already been confirmed"))
        error_message = None
        if abs(self.amount_total_electronic_invoice - self.amount_total) > 1:  # TODO may be config
            error_message = _("Total amount does not match the XML amount")
        if (
            not self.company_id.sucursal_MR or not self.company_id.terminal_MR
        ):  # TODO make constraint
            error_message = _("Please configure the shopping journal, terminal and branch")
        if not self.state_invoice_partner:
            error_message = _("You must first select the response type for the uploaded file.")

        if error_message:
            self.state_send_invoice = "error"
            self.message_post(subject=_("Error"), body=error_message)
        return error_message

    def retry(self, token, message_body, message):  # TODO docstring
        response_json = cr_edi.api.query_document(
            clave="{}-{}".format(
                self.number_electronic,
                self.consecutive_number_receiver,  # TODO why?
            ),
            token=token,
            client_id=self.company_id.frm_ws_ambiente,
        )
        status = response_json.get("status")
        if status == 200:
            self.state_send_invoice = response_json.get("ind-estado")
            self.xml_respuesta_tributacion = response_json.get("respuesta-xml")
            self.fname_xml_respuesta_tributacion = "ACH_{}-{}.xml".format(
                self.number_electronic,
                self.consecutive_number_receiver,
            )
            _logger.error("E-INV CR - Estado Documento:{}".format(self.state_send_invoice))
            message_body += (
                "<p><b>You have sent Receiver Message</b>"
                "<br /><b>Document:</b> {}"
                "<br /><b>Consecutive:</b> {}"
                "<br/><b>Message:</b> {}"
                "</p>".format(
                    self.number_electronic,
                    self.consecutive_number_receiver,
                    message,
                )
            )
            self.message_post(body=message_body, subtype="mail.mt_note", content_subtype="html")
        elif status == 400:
            self.state_send_invoice = "ne"
            _logger.error("MAB - Document Acceptance: {}-{} not found in ISR.").format(
                self.number_electronic, self.consecutive_number_receiver
            )
        else:
            _logger.error("MAB - Unexpected error in Send Acceptance File - Aborting")

    @api.onchange("partner_id", "company_id")
    def _onchange_partner_id(self):
        """Set payment_methods_id and tipo_documento based on partner"""
        super(AccountInvoice, self)._onchange_partner_id()
        self.payment_methods_id = self.partner_id.payment_methods_id

        if self.partner_id and self.partner_id.identification_id and self.partner_id.vat:
            if self.partner_id.country_id.code == "CR":
                self.tipo_documento = "FE"
            else:
                self.tipo_documento = "FEE"
        else:
            self.tipo_documento = "TE"

    @api.constrains("number_electronic")
    def _verify_number_electronic(self):
        for invoice in self:
            if invoice.number_electronic and len(invoice.number_electronic) != 50:
                raise ValidationError(_("The Electronic Number must have 50 chars"))

    @api.model
    def _get_invoices_to_query(self):
        out_invoices = self.env["account.move"].search(
            [
                ("move_type", "in", ["out_invoice", "out_refund"]),
                ("state", "in", ["open", "paid"]),
                ("state_tributacion", "in", ["recibido", "procesando", "ne", "error"]),
            ]
        )

        in_invoices = self.env["account.move"].search(
            [
                ("move_type", "=", "in_invoice"),
                ("state", "in", ["open", "paid"]),
                ("tipo_documento", "=", "FEC"),
                ("state_send_invoice", "in", ["procesando", "ne", "error"]),
                ("number_electronic", "!=", False),
            ]
        )
        return out_invoices | in_invoices

    def _process_rejection(self, state):
        """Process invoice rejection

        Args:
            state (str): State to be setted in invoice
        """
        self.state_email = "fe_error"
        self.state_tributacion = state

        tree = etree.fromstring(base64.b64decode(self.xml_respuesta_tributacion))
        namespaces = tree.nsmap
        inv_xmlns = namespaces.pop(None)
        namespaces["inv"] = inv_xmlns
        detalle_tag = tree.find("inv:DetalleMensaje", namespaces=namespaces)

        self.electronic_invoice_return_message = detalle_tag.text

    @api.model
    def query_all_documents_needed(self, max_invoices=10):
        """Query all documents that need to be processed by API

        Args:
            max_invoices (int, optional): Max number to be queried in single call. Defaults to 10.
        """
        invoices = self._get_invoices_to_query()

        total_invoices = len(invoices)
        current_invoice = 0

        _logger.info("E-INV CR - Query ISR - Invoices to Verify: {}".format(total_invoices))
        for invoice in invoices[:max_invoices]:
            current_invoice += 1
            _logger.info(
                _("E-INV CR - Query ISR - Invoice {} / {}  -  number:{}").format(
                    current_invoice, total_invoices, invoice.number_electronic
                )
            )
            response_json = cr_edi.api.query_document(
                clave=invoice.number_electronic,
                token=invoice.company_id.get_token(),
                client_id=invoice.company_id.frm_ws_ambiente,
            )

            status = response_json["status"]

            state = response_json.get("ind-estado")
            if status != 200:
                if status == 400:
                    invoice.state_tributacion = "ne"
                    _logger.warning(
                        _("E-INV CR - Document: {} not found in ISR. State: {}").format(
                            invoice.number_electronic, state
                        )
                    )
                else:
                    _logger.error("E-INV CR - Unexpected error in Tax Consultation - Aborting")
                    continue

                if invoice.move_type == "in_invoice":
                    invoice.state_send_invoice = state
                else:
                    invoice.state_tributacion = state

                if state == "error":
                    continue

                invoice.fname_xml_respuesta_tributacion = (
                    "AHC_" + invoice.number_electronic + ".xml"
                )
                invoice.xml_respuesta_tributacion = response_json.get("respuesta-xml")

                if state == "aceptado":
                    invoice._send_mail()
                elif state == "firma_invalida":
                    invoice.state_email = "fe_error"
                    _logger.warning("Mail no sended - Invoice rejected")
                elif state == "rechazado":
                    invoice._process_rejection(state)

    def action_check_hacienda(self):
        """Exec update_state in records selected"""
        for invoice in self.filtered("to_process"):
            invoice.update_state()

    @api.model
    def _check_hacienda_for_mrs(self, max_invoices=10):
        # TODO may be replace with only send_mrs_to_hacienda
        invoices = self.env["account.move"].search(
            [
                ("move_type", "in", ["in_invoice", "in_refund"]),
                ("state", "in", ["open", "paid"]),
                ("xml_supplier_approval", "!=", False),
                ("state_invoice_partner", "!=", False),
                (
                    "state_send_invoice",
                    "not in",
                    ["aceptado", "rechazado", "error", "na"],
                ),
            ],
            limit=max_invoices,
        )

        invoices.send_mrs_to_hacienda()

    # UNUSED
    def action_create_fec(self):
        self.generate_and_send_invoices()

    @api.model
    def _send_invoices_to_hacienda(self, max_invoices=10):
        # TODO may be replaced with generate_and_send_invoices
        _logger.info("FECR - Running Valid ISR")
        invoices = self.env["account.move"].search(
            [
                ("to_process", "=", True),
                ("move_type", "in", ["out_invoice", "out_refund"]),
                ("state", "in", ["open", "paid"]),
                ("number_electronic", "!=", False),
                ("invoice_date", ">=", "2018-10-01"),
                "|",
                ("state_tributacion", "=", False),
                ("state_tributacion", "=", "ne"),
            ],
            order="number_electronic",
            limit=max_invoices,
        )
        invoices.generate_and_send_invoices()

    def _create_xml_comprobante(self):
        """Create and set XML from invoice data"""
        self.date_issuance = cr_edi.utils.get_time_cr()

        # BUG CORREGIR NUMERO DE FACTURA NO SE GUARDA EN LA REFERENCIA DE LA NC CUANDO SE CREA MANUALMENTE
        if not self.invoice_origin:
            self.invoice_origin = self.invoice_id.display_name
        xml_raw = cr_edi.gen_xml.gen(self)
        xml_signed = cr_edi.utils.sign_xml(
            cert=self.company_id.signature,
            pin=self.company_id.frm_pin,
            xml=xml_raw,
        )

        self.fname_xml_comprobante = "{}_{}.xml".format(self.tipo_documento, self.number_electronic)
        self.xml_comprobante = base64.encodebytes(xml_signed)
        _logger.debug("E-INV CR - SIGNED XML:{}".format(self.fname_xml_comprobante))

    @api.constrains("sequence")
    def _verify_sequence(self):
        """Ensure sequence to be numeric

        Raises:
            ValidationError: If sequence is not numeric
        """
        for invoice in self:
            if invoice.sequence and not invoice.sequence.isdigit():
                raise ValidationError(_("Sequence only can be numeric"))

    def _send_xml(self):
        """Call cr_edi.api.send_xml with invoice data

        Returns:
            dict: response_json from API
        """
        response_json = cr_edi.api.send_xml(
            client_id=self.company_id.frm_ws_ambiente,
            token=self.company_id.get_token(),
            xml=base64.b64decode(self.xml_comprobante),
            date=self.date_issuance,
            electronic_number=self.number_electronic,
            issuer=self.company_id,
            receiver=self.partner_id,
        )
        return response_json

    def generate_and_send_invoices(self):
        """Generate XML, send it and procees response from that API call."""
        for invoice in self:
            if not invoice.xml_comprobante:
                invoice._create_xml_comprobante()
            response_json = invoice._send_xml()

            response_status = response_json.get("status")
            response_text = response_json.get("text")

            if 200 <= response_status <= 299:
                if invoice.tipo_documento == "FEC":
                    invoice.state_send_invoice = "procesando"
                else:
                    invoice.state_tributacion = "procesando"
                invoice.electronic_invoice_return_message = response_text
                continue

            if response_text.find("ya fue recibido anteriormente") != -1:
                if invoice.tipo_documento == "FEC":
                    invoice.state_send_invoice = "procesando"
                else:
                    invoice.state_tributacion = "procesando"
                invoice.message_post(
                    subject=_("Error"),
                    body=_("Already received previously, it is time to consult"),
                )
                continue

            invoice.message_post(subject=_("Error"), body=response_text)
            _logger.error("E-INV CR  - Invoice: {}  Status: {} Error sending XML: {}").format(
                invoice.number_electronic, response_status, response_text
            )
            invoice.electronic_invoice_return_message = response_text
            invoice.state_tributacion = "error"

        _logger.debug("E-INV CR - Validate ISR - Successfully completed")

    def _get_sequence(self):
        """Get sequence object from tipo_documento

        Returns:
            ir.sequence: Sequence to be used to get next id
        """
        journal = self.journal_id
        TYPE_TO_SEQUENCE = {
            "FE": journal.FE_sequence_id,
            "TE": journal.TE_sequence_id,
            "FEE": journal.FEE_sequence_id,
            "NC": journal.NC_sequence_id,
            "FEC": self.company_id.FEC_sequence_id,  # TODO why
        }
        sequence = TYPE_TO_SEQUENCE[self.tipo_documento]
        return sequence

    def action_post(self):
        """Validates invoice and create sequence and number electronic"""
        res = super(AccountInvoice, self).action_post()
        for invoice in self.filtered("to_process"):
            sequence_obj = invoice._get_sequence()
            invoice.electronic_sequence = cr_edi.utils.compute_full_sequence(
                branch=invoice.journal_id.sucursal,
                terminal=invoice.journal_id.terminal,
                doc_type=invoice.tipo_documento,
                sequence=sequence_obj.next_by_id(),
            )
            invoice.number_electronic = cr_edi.utils.get_number_electronic(
                issuer=invoice.company_id,
                full_sequence=invoice.electronic_sequence,
            )
            invoice.state_send_invoice = False  # TODO why
        return res
