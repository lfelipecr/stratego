from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _reverse_moves(self, default_values_list=None, cancel=False):
        """Adding invoice_id, reference_code_id, invoice_payment_term_id and tipo_documento to
        the reversed moves.
        :param default_values_list: A list of default values to consider per move.
                                    ('type' & 'reversed_entry_id' are computed in the method).
        :return: An account.move recordset, reverse of the current self.
        """
        if not self.env.user.company_id.frm_ws_ambiente:
            result = super(AccountMove, self)._reverse_moves(default_values_list, cancel)
            return result

        if not default_values_list:
            default_values_list = [{} for move in self]

        if cancel:
            lines = self.mapped("line_ids")
            # Avoid maximum recursion depth.
            if lines:
                lines.remove_move_reconcile()

        reverse_type_map = {
            "entry": "entry",
            "out_invoice": "out_refund",
            "out_refund": "entry",
            "in_invoice": "in_refund",
            "in_refund": "entry",
            "out_receipt": "entry",
            "in_receipt": "entry",
        }

        move_vals_list = []
        for move, default_values in zip(self, default_values_list):
            default_values.update(
                {
                    "move_type": reverse_type_map[move.move_type],
                    "reversed_entry_id": move.id,
                    "invoice_id": move.id,
                    "reference_code_id": move.reference_code_id,
                    "invoice_payment_term_id": move.invoice_payment_term_id.id,
                    "tipo_documento": "NC",
                }
            )
            move_vals_list.append(
                move.with_context(move_reverse_cancel=cancel)._reverse_move_vals(
                    default_values, cancel=cancel
                )
            )

        reverse_moves = self.env["account.move"].create(move_vals_list)
        for move, reverse_move in zip(self, reverse_moves.with_context(check_move_validity=False)):
            # Update amount_currency if the date has changed.
            if move.date != reverse_move.date:
                for line in reverse_move.line_ids:
                    if line.currency_id:
                        line._onchange_currency()
            reverse_move._recompute_dynamic_lines(recompute_all_taxes=False)
        reverse_moves._check_balanced()

        # Reconcile moves together to cancel the previous one.
        if cancel:
            reverse_moves.with_context(move_reverse_cancel=cancel)._post(soft=False)
            for move, reverse_move in zip(self, reverse_moves):
                accounts = move.mapped("line_ids.account_id").filtered(
                    lambda account: account.reconcile or account.internal_type == "liquidity"
                )
                for account in accounts:
                    (move.line_ids + reverse_move.line_ids).filtered(
                        lambda line: line.account_id == account and not line.reconciled
                    ).with_context(move_reverse_cancel=cancel).reconcile()

        return reverse_moves
