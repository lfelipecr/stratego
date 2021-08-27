import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    @api.model
    def _message_route_process(self, message, message_dict, routes):
        self = self.with_context(attachments_mime_plainxml=True)  # import XML attachments as text
        # postpone setting message_dict.partner_ids after message_post, to avoid double notifications
        original_partner_ids = message_dict.pop("partner_ids", [])
        logging.info("------- Entra -------")
        thread_id = False
        for model, thread_id, custom_values, user_id, _alias in routes or ():
            subtype_id = False
            related_user = self.env["res.users"].browse(user_id)
            Model = self.env[model].with_context(
                mail_create_nosubscribe=True, mail_create_nolog=True
            )
            if not (
                thread_id and hasattr(Model, "message_update") or hasattr(Model, "message_new")
            ):
                raise ValueError(
                    "Undeliverable mail with Message-Id %s, model %s does not accept incoming emails"
                    % (message_dict["message_id"], model)
                )

            # disabled subscriptions during message_new/update to avoid having the system user running the
            # email gateway become a follower of all inbound messages
            ModelCtx = Model.with_user(related_user).sudo()
            if thread_id and hasattr(ModelCtx, "message_update"):
                thread = ModelCtx.browse(thread_id)
                thread.message_update(message_dict)
            else:
                # if a new thread is created, parent is irrelevant
                message_dict.pop("parent_id", None)
                if not custom_values:
                    custom_values = {}
                custom_values.update({"move_type": "in_invoice"})
                thread = ModelCtx.message_new(message_dict, custom_values)
                logging.info("------- Factura(? creada --------")
                logging.info(thread)
                thread_id = thread.id
                subtype_id = thread._creation_subtype().id

            # replies to internal message are considered as notes, but parent message
            # author is added in recipients to ensure he is notified of a private answer
            parent_message = False
            if message_dict.get("parent_id"):
                parent_message = self.env["mail.message"].sudo().browse(message_dict["parent_id"])
            partner_ids = []
            if not subtype_id:
                if message_dict.get("is_internal"):
                    subtype_id = self.env["ir.model.data"].xmlid_to_res_id("mail.mt_note")
                    if parent_message and parent_message.author_id:
                        partner_ids = [parent_message.author_id.id]
                else:
                    subtype_id = self.env["ir.model.data"].xmlid_to_res_id("mail.mt_comment")

            post_params = dict(subtype_id=subtype_id, partner_ids=partner_ids, **message_dict)
            # remove computational values not stored on mail.message and avoid warnings when creating it
            for x in (
                "from",
                "to",
                "cc",
                "recipients",
                "references",
                "in_reply_to",
                "bounced_email",
                "bounced_message",
                "bounced_msg_id",
                "bounced_partner",
            ):
                post_params.pop(x, None)
            new_msg = False
            if thread._name == "mail.thread":  # message with parent_id not linked to record
                new_msg = thread.message_notify(**post_params)
            else:
                # parsing should find an author independently of user running mail gateway, and ensure it is not odoobot
                partner_from_found = message_dict.get("author_id") and message_dict[
                    "author_id"
                ] != self.env["ir.model.data"].xmlid_to_res_id("base.partner_root")
                thread = thread.with_context(mail_create_nosubscribe=not partner_from_found)
                new_msg = thread.message_post(**post_params)

            logging.info("A veeeeer")

            if new_msg and original_partner_ids:
                # postponed after message_post, because this is an external message and we don't want to create
                # duplicate emails due to notifications
                new_msg.write({"partner_ids": original_partner_ids})

            #  Add xml attached on email to invoice and call load_xml_data()
            if model == "account.move":
                logging.info(thread)
                thread.move_type = "in_invoice"
                xml_attachment = self.env["ir.attachment"].search(
                    [
                        ("res_id", "=", thread.id),
                        ("res_model", "=", model),
                    ]
                )
                logging.info(xml_attachment)
                logging.info("store_fname: " + xml_attachment.store_fname)
                logging.info("name: " + xml_attachment.name)
                logging.info("display_name: " + xml_attachment.display_name)
                logging.info("res_name: " + xml_attachment.res_name)
                logging.info("------- probando -------")
                #  logging.info(message_dict.get("attachments"))
                if xml_attachment and xml_attachment.name[-3:] == "xml":
                    logging.info("------- Hay adjunto -------")
                    thread.fname_xml_supplier_approval = xml_attachment.name
                    thread.xml_supplier_approval = xml_attachment.datas
                    # thread.fname_xml_comprobante = xml_attachment.datas_fname
                    # thread.xml_comprobante = xml_attachment.datas
                    thread.load_xml_data()
                    logging.info(thread)

        return thread_id
