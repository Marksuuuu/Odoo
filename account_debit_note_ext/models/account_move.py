# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from itertools import groupby
from odoo.exceptions import RedirectWarning, UserError, ValidationError, AccessError
from odoo.tools import float_is_zero, float_compare, safe_eval, date_utils, email_split, email_escape_char, email_re
from odoo.tools.misc import formatLang, format_date, get_lang


class AccountMove(models.Model):
    _inherit = "account.move"

    is_debit_note = fields.Boolean(default=False)
    is_mui_cip_transaction = fields.Boolean(default=False)
    transfer_status = fields.Selection(selection=[
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], required=True, readonly=True, copy=False, tracking=True,
        default='pending')


    def _get_sequence(self):
        journal = self.journal_id
        if self.is_debit_note and self.type == 'out_invoice':
            return journal.debit_sequence_id
        else:
            return super(AccountMove, self)._get_sequence()

    def _prepare_bill_journal_items_reverse(self, invoice_line_ids, amount_total, journal, partner_id):
        vals = []
        name_list = [line.name for line in invoice_line_ids]
        asset_account_list = [line.asset_category_id for line in invoice_line_ids][0]
        total = invoice_line_ids.currency_id.compute(amount_total, journal.company_id.currency_id)

        vals_line_debit = {
            'name': "; ".join(name_list),
            'partner_id': partner_id.id,
            'credit': 0.0,
            'debit': total,
            'asset_category_id': asset_account_list.id,
            'account_id': asset_account_list.account_asset_id.id
        }
        vals.append(vals_line_debit)

        vals_line_credit = {
            'name': "",
            'partner_id': partner_id.id,
            'credit': total,
            'debit': 0.0,
            'asset_category_id': "",
            'account_id': journal.default_credit_account_id.id,
        }
        vals.append(vals_line_credit)

        return vals

    @api.onchange('invoice_line_ids')
    def _onchange_invoice_line_ids(self):
        if self.is_debit_note:
            current_invoice_lines = self.line_ids.filtered(lambda line: not line.exclude_from_invoice_tab)
            others_lines = self.line_ids - current_invoice_lines
            if others_lines and current_invoice_lines - self.invoice_line_ids:
                others_lines[0].recompute_tax_line = True
            self.line_ids = others_lines + self.invoice_line_ids
        else:
            return super(AccountMove, self)._onchange_invoice_line_ids()

    def action_post(self):
        if self.is_debit_note:
            for rec in self.line_ids:
                if rec.product_id:
                    rec.write({
                        'debit_line': True
                    })
        context = dict(self.env.context)
        if self.filtered(lambda x: x.journal_id.post_at == 'bank_rec').mapped('line_ids.payment_id').filtered(
                lambda x: x.state != 'reconciled'):
            raise UserError(
                _("A payment journal entry generated in a journal configured to post entries only when payments are reconciled with a bank statement cannot be manually posted. Those will be posted automatically after performing the bank reconciliation."))

        if self.env.context.get('default_type'):
            del context['default_type']
            self = self.with_context(context=context)
        try:
            if not context['default_is_mui_cip_transaction']:
                for inv in self:
                    context.pop('default_type', None)
                    for mv_line in inv.invoice_line_ids:
                        mv_line.with_context(context=context).asset_create()
        except KeyError:
            return self.post()

        return self.post()

    def button_cancel(self):
        self.mapped('line_ids').remove_move_reconcile()
        self.write({'state': 'cancel',
                    'transfer_status': 'cancel'})

    def action_create_journal(self):
        bill_ids = self.browse(self.env.context['active_ids'])
        journal = self.env["account.journal"].search([("name", "=", "Miscellaneous Operations")], limit=1)

        date = self._context.get('force_period_date', fields.Date.context_today(self))

        for bill_id in bill_ids:
            name_list = [line.name for line in bill_id.invoice_line_ids]
            bill_product = [line.product_id.id for line in bill_id.invoice_line_ids][0]
            product_asset = self.env["product.product"].search([("id", "=", bill_product)], limit=1)
            asset = self.env["account.asset.asset"].search([("invoice_ids", "=", bill_id.id)])

            if bill_id.transfer_status == 'done':
                raise UserError(_("Products from {} already have an asset!").format(bill_id.name))

            else:
                new_account_move = self.env['account.move'].create({
                    'journal_id': journal.id,
                    'line_ids': [(0, 0, line) for line in
                                 self._prepare_bill_journal_items_reverse(bill_id.invoice_line_ids,
                                                                          bill_id.amount_total,
                                                                          journal, bill_id.partner_id)],
                    'date': date,
                    'ref': "; ".join(name_list),
                    'partner_id': bill_id.partner_id.id,
                    'type': 'entry',
                })
                new_account_move.post()

                for line in bill_id.invoice_line_ids:
                    new_asset = self.env['account.asset.asset'].create({
                        'name': line.name,
                        'category_id': product_asset.asset_category_id.id,
                        'date': date,
                        'code': line.name,
                        'value': line.price_subtotal,
                        'partner_id': bill_id.partner_id.id,
                        'invoice_ids': bill_id,
                        'method_number': product_asset.asset_category_id.method_number,
                        'method_period': product_asset.asset_category_id.method_period,
                        'type': 'purchase',
                    })

                bill_id.write({
                    'transfer_status': 'done'
                })

    def action_create_journal_combined(self):
        bill_ids = self.browse(self.env.context['active_ids'])
        for bill_id in bill_ids:
            if not bill_id.ref:
                raise UserError(_("Vendor Reference should not be blank!"))
        ppa_ref = [bill_id.ref for bill_id in bill_ids][0].split(", ")
        bill_product = [bill_id.product_id.id for bill_id in bill_ids.invoice_line_ids][0]
        product_asset = self.env["product.product"].search([("id", "=", bill_product)], limit=1)

        asset = self.env["account.asset.asset"].search([("ppa_reference", "=", ppa_ref[-1])])
        journal = self.env["account.journal"].search([("name", "=", "Miscellaneous Operations")], limit=1)

        name_vals = []
        invoice_ids = [bill_id.id for bill_id in bill_ids]
        date = self._context.get('force_period_date', fields.Date.context_today(self))
        total = abs(sum([bill_id.amount_total_signed for bill_id in bill_ids]))
        # converted_total = bill_ids.amount_total_signed.currency_id.compute(total, journal.company_id.currency_id)

        for bill_id in bill_ids:
            name_list = [line.name for line in bill_id.invoice_line_ids]
            name_vals.append("; ".join(name_list))
            bill_id.write({
                'transfer_status': 'done'
            })

            new_account_move = self.env['account.move'].create({
                'journal_id': journal.id,
                'line_ids': [(0, 0, line) for line in
                             self._prepare_bill_journal_items_reverse(bill_id.invoice_line_ids,
                                                                      bill_id.amount_total,
                                                                      journal, bill_id.partner_id)],
                'date': date,
                'ref': "; ".join(name_list),
                'partner_id': bill_id.partner_id.id,
                'type': 'entry',
            })
            new_account_move.post()

        if asset:
            asset_name = asset.name
            asset_value = asset.value
            # asset_invoice = asset.invoice_ids
            asset.write({
                'name': asset_name + "; " + "; ".join(name_vals),
                'value': asset_value + total,

            })
            for invoice_id in invoice_ids:
                asset.write({
                    'invoice_ids': [(4, invoice_id)]
                })

        else:
            new_asset = self.env['account.asset.asset'].create({
                'name': "; ".join(name_vals),
                'category_id': product_asset.asset_category_id.id,
                'date': date,
                'code': "; ".join(name_vals),
                'value': total,
                'invoice_ids': invoice_ids,
                'method_number': product_asset.asset_category_id.method_number,
                'method_period': product_asset.asset_category_id.method_period,
                'ppa_reference': ppa_ref[-1],
                'type': 'purchase',
            })


    def post(self):
        # `user_has_group` won't be bypassed by `sudo()` since it doesn't change the user anymore.
        if not self.env.su and not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_("You don't have the access rights to post an invoice."))
        for move in self:
            if move.state == 'posted':
                raise UserError(_('The entry {}  is already posted.').format(move.name))
            if not move.line_ids.filtered(lambda line: not line.display_type):
                raise UserError(_('You need to add a line before posting.'))
            if move.auto_post and move.date > fields.Date.today():
                date_msg = move.date.strftime(get_lang(self.env).date_format)
                raise UserError(_('This move is configured to be auto-posted on {}').format(date_msg))

            if not move.partner_id:
                if move.is_sale_document():
                    raise UserError(
                        _("The field 'Customer' is required, please complete it to validate the Customer Invoice."))
                elif move.is_purchase_document():
                    raise UserError(
                        _("The field 'Vendor' is required, please complete it to validate the Vendor Bill."))

            if move.is_invoice(include_receipts=True) and float_compare(move.amount_total, 0.0,
                                                                        precision_rounding=move.currency_id.rounding) < 0:
                raise UserError(
                    _("You cannot validate an invoice with a negative total amount. You should create a credit note instead. Use the action menu to transform it into a credit note or refund."))

            # Handle case when the invoice_date is not set. In that case, the invoice_date is set at today and then,
            # lines are recomputed accordingly.
            # /!\ 'check_move_validity' must be there since the dynamic lines will be recomputed outside the 'onchange'
            # environment.
            if not move.invoice_date and move.is_invoice(include_receipts=True):
                move.invoice_date = fields.Date.context_today(self)
                move.with_context(check_move_validity=False)._onchange_invoice_date()

            # When the accounting date is prior to the tax lock date, move it automatically to the next available date.
            # /!\ 'check_move_validity' must be there since the dynamic lines will be recomputed outside the 'onchange'
            # environment.
            if (move.company_id.tax_lock_date and move.date <= move.company_id.tax_lock_date) and (
                    move.line_ids.tax_ids or move.line_ids.tag_ids):
                move.date = move.company_id.tax_lock_date + timedelta(days=1)
                move.with_context(check_move_validity=False)._onchange_currency()

        # Create the analytic lines in batch is faster as it leads to less cache invalidation.
        self.mapped('line_ids').create_analytic_lines()
        for move in self.sorted(lambda m: (m.date, m.ref or '', m.id)):
            if move.auto_post and move.date > fields.Date.today():
                raise UserError(_('This move is configured to be auto-posted on {}').format(
                    move.date.strftime(get_lang(self.env).date_format)))

            # Fix inconsistencies that may occure if the OCR has been editing the invoice at the same time of a user. We force the
            # partner on the lines to be the same as the one on the move, because that's the only one the user can see/edit.
            wrong_lines = move.is_invoice() and move.line_ids.filtered(
                lambda aml: aml.partner_id != move.commercial_partner_id and not aml.display_type)
            if wrong_lines:
                wrong_lines.partner_id = move.commercial_partner_id.id

            move.message_subscribe([p.id for p in [move.partner_id] if p not in move.sudo().message_partner_ids])

            to_write = {'state': 'posted'}

            if move.name == '/':
                # Get the journal's sequence.
                sequence = move._get_sequence()
                if not sequence:
                    raise UserError(_('Please define a sequence on your journal.'))

                # Consume a new number.
                to_write['name'] = sequence.with_context(ir_sequence_date=move.date).next_by_id()

            move.write(to_write)

            # Compute 'ref' for 'out_invoice'.
            if move.type == 'out_invoice' and not move.invoice_payment_ref:
                to_write = {
                    'invoice_payment_ref': move._get_invoice_computed_reference(),
                    'line_ids': []
                }
                for line in move.line_ids.filtered(
                        lambda line: line.account_id.user_type_id.type in ('receivable', 'payable')):
                    if self.is_debit_note and line.debit == 0.0:
                        continue
                    to_write['line_ids'].append((1, line.id, {'name': to_write['invoice_payment_ref']}))
                move.write(to_write)

            if move == move.company_id.account_opening_move_id and not move.company_id.account_bank_reconciliation_start:
                # For opening moves, we set the reconciliation date threshold
                # to the move's date if it wasn't already set (we don't want
                # to have to reconcile all the older payments -made before
                # installing Accounting- with bank statements)
                move.company_id.account_bank_reconciliation_start = move.date

        for move in self:
            if not move.partner_id: continue
            partners = (move.partner_id | move.partner_id.commercial_partner_id)
            if move.type.startswith('out_'):
                partners._increase_rank('customer_rank')
            elif move.type.startswith('in_'):
                partners._increase_rank('supplier_rank')
            else:
                continue

        # Trigger action for paid invoices in amount is zero
        self.filtered(
            lambda m: m.is_invoice(include_receipts=True) and m.currency_id.is_zero(m.amount_total)
        ).action_invoice_paid()

        # Force balance check since nothing prevents another module to create an incorrect entry.
        # This is performed at the very end to avoid flushing fields before the whole processing.
        self._check_balanced()
        return True

    def _recompute_payment_terms_lines(self):
        ''' Compute the dynamic payment term lines of the journal entry.'''
        self.ensure_one()
        in_draft_mode = self != self._origin
        today = fields.Date.context_today(self)
        self = self.with_context(force_company=self.journal_id.company_id.id)

        def _get_payment_terms_computation_date(self):
            ''' Get the date from invoice that will be used to compute the payment terms.
                :param self:    The current account.move record.
                :return:        A datetime.date object.
                '''
            if self.invoice_payment_term_id:
                return self.invoice_date or today
            else:
                return self.invoice_date_due or self.invoice_date or today

        def _get_payment_terms_account(self, payment_terms_lines):
            ''' Get the account from invoice that will be set as receivable / payable account.
                :param self:                    The current account.move record.
                :param payment_terms_lines:     The current payment terms lines.
                :return:                        An account.account record.
                '''

            if payment_terms_lines:
                # Retrieve account from previous payment terms lines in order to allow the user to set a custom one.
                return payment_terms_lines[0].account_id

            elif self.partner_id:
                # Retrieve account from partner.
                if self.is_sale_document(include_receipts=True):
                    return self.partner_id.property_account_receivable_id
                else:
                    return self.partner_id.property_account_payable_id

            else:
                # Search new account.
                domain = [
                    ('company_id', '=', self.company_id.id),
                    ('internal_type', '=',
                     'receivable' if self.type in ('out_invoice', 'out_refund', 'out_receipt') else 'payable'),
                ]
                return self.env['account.account'].search(domain, limit=1)

        def _compute_payment_terms(self, date, total_balance, total_amount_currency):
            ''' Compute the payment terms.
                :param self:                    The current account.move record.
                :param date:                    The date computed by '_get_payment_terms_computation_date'.
                :param total_balance:           The invoice's total in company's currency.
                :param total_amount_currency:   The invoice's total in invoice's currency.
                :return:                        A list <to_pay_company_currency, to_pay_invoice_currency, due_date>.
                '''
            if self.invoice_payment_term_id:
                to_compute = self.invoice_payment_term_id.compute(total_balance, date_ref=date,
                                                                  currency=self.company_id.currency_id)
                if self.currency_id != self.company_id.currency_id:
                    # Multi-currencies.
                    to_compute_currency = self.invoice_payment_term_id.compute(total_amount_currency, date_ref=date,
                                                                               currency=self.currency_id)
                    return [(b[0], b[1], ac[1]) for b, ac in zip(to_compute, to_compute_currency)]
                else:
                    # Single-currency.
                    return [(b[0], b[1], 0.0) for b in to_compute]
            else:
                return [(fields.Date.to_string(date), total_balance, total_amount_currency)]

        def _compute_diff_payment_terms_lines(self, existing_terms_lines, account, to_compute):
            ''' Process the result of the '_compute_payment_terms' method and creates/updates corresponding invoice lines.
                :param self:                    The current account.move record.
                :param existing_terms_lines:    The current payment terms lines.
                :param account:                 The account.account record returned by '_get_payment_terms_account'.
                :param to_compute:              The list returned by '_compute_payment_terms'.
                '''
            # As we try to update existing lines, sort them by due date.
            existing_terms_lines = existing_terms_lines.sorted(lambda line: line.date_maturity or today)
            existing_terms_lines_index = 0

            # Recompute amls: update existing line or create new one for each payment term.
            new_terms_lines = self.env['account.move.line']
            for date_maturity, balance, amount_currency in to_compute:
                currency = self.journal_id.company_id.currency_id
                if currency and currency.is_zero(balance) and len(to_compute) > 1:
                    continue

                if existing_terms_lines_index < len(existing_terms_lines):
                    # Update existing line.
                    candidate = existing_terms_lines[existing_terms_lines_index]

                    existing_terms_lines_index += 1
                    candidate.update({
                        'date_maturity': date_maturity,
                        'amount_currency': -amount_currency,
                        'debit': balance < 0.0 and -balance or 0.0,
                        'credit': balance > 0.0 and balance or 0.0,
                    })
                else:
                    # Create new line.
                    create_method = in_draft_mode and self.env['account.move.line'].new or self.env[
                        'account.move.line'].create
                    candidate = create_method({
                        'name': self.invoice_payment_ref or '',
                        'debit': balance < 0.0 and -balance or 0.0,
                        'credit': balance > 0.0 and balance or 0.0,
                        'quantity': 1.0,
                        'amount_currency': -amount_currency,
                        'date_maturity': date_maturity,
                        'move_id': self.id,
                        'currency_id': self.currency_id.id if self.currency_id != self.company_id.currency_id else False,
                        'account_id': account.id,
                        'partner_id': self.commercial_partner_id.id,
                        'exclude_from_invoice_tab': True,
                    })
                new_terms_lines += candidate
                if in_draft_mode:
                    candidate._onchange_amount_currency()
                    candidate._onchange_balance()
            return new_terms_lines

        if self.is_debit_note:
            existing_terms_lines = self.line_ids.filtered(lambda line: line.account_id.user_type_id.type == 'payable')
            others_lines = self.line_ids.filtered(
                lambda line: line.account_id.user_type_id.type != 'payable')
        else:
            existing_terms_lines = self.line_ids.filtered(
                lambda line: line.account_id.user_type_id.type in ('receivable', 'payable'))

            others_lines = self.line_ids.filtered(
                lambda line: line.account_id.user_type_id.type not in ('receivable', 'payable'))
        company_currency_id = (self.company_id or self.env.company).currency_id
        total_balance = sum(others_lines.mapped(lambda l: company_currency_id.round(l.balance)))
        total_amount_currency = sum(others_lines.mapped('amount_currency'))

        if not others_lines:
            self.line_ids -= existing_terms_lines
            return

        computation_date = _get_payment_terms_computation_date(self)
        account = _get_payment_terms_account(self, existing_terms_lines)
        to_compute = _compute_payment_terms(self, computation_date, total_balance, total_amount_currency)
        new_terms_lines = _compute_diff_payment_terms_lines(self, existing_terms_lines, account, to_compute)

        # Remove old terms lines that are no longer needed.
        self.line_ids -= existing_terms_lines - new_terms_lines

        if new_terms_lines:
            self.invoice_payment_ref = new_terms_lines[-1].name or ''
            self.invoice_date_due = new_terms_lines[-1].date_maturity

    @api.onchange('purchase_vendor_bill_id', 'purchase_id')
    def _onchange_purchase_auto_complete(self):
        ''' Load from either an old purchase order, either an old vendor bill.

        When setting a 'purchase.bill.union' in 'purchase_vendor_bill_id':
        * If it's a vendor bill, 'invoice_vendor_bill_id' is set and the loading is done by '_onchange_invoice_vendor_bill'.
        * If it's a purchase order, 'purchase_id' is set and this method will load lines.

        /!\ All this not-stored fields must be empty at the end of this function.
        '''
        if self.purchase_vendor_bill_id.vendor_bill_id:
            self.invoice_vendor_bill_id = self.purchase_vendor_bill_id.vendor_bill_id
            self._onchange_invoice_vendor_bill()
        elif self.purchase_vendor_bill_id.purchase_order_id:
            self.purchase_id = self.purchase_vendor_bill_id.purchase_order_id
        self.purchase_vendor_bill_id = False

        if not self.purchase_id:
            return

        # Copy partner.
        self.partner_id = self.purchase_id.partner_id
        self.fiscal_position_id = self.purchase_id.fiscal_position_id
        self.invoice_payment_term_id = self.purchase_id.payment_term_id
        self.currency_id = self.purchase_id.currency_id
        self.company_id = self.purchase_id.company_id

        # Copy purchase lines.
        po_lines = self.purchase_id.order_line - self.line_ids.mapped('purchase_line_id')
        new_lines = self.env['account.move.line']
        for line in po_lines.filtered(lambda l: not l.display_type):
            new_line = new_lines.new(line._prepare_account_move_line(self))
            new_line.account_id = new_line._get_computed_account()
            new_line._onchange_price_subtotal()
            new_lines += new_line
        new_lines._onchange_mark_recompute_taxes()
        new_lines.onchange_asset_category_id()

        # Compute invoice_origin.
        origins = set(self.line_ids.mapped('purchase_line_id.order_id.name'))
        self.invoice_origin = ','.join(list(origins))

        # Compute ref.
        refs = self._get_invoice_reference()
        if self.is_mui_cip_transaction:
            self.ref = ', '.join(refs[0:-1])
            # self.ref = refs[-1]

        else:
            self.ref = ', '.join(refs)

            # Compute invoice_payment_ref.
            if len(refs) == 1:
                self.invoice_payment_ref = refs[0]

        self.purchase_id = False
        self._onchange_currency()
        self.invoice_partner_bank_id = self.bank_partner_id.bank_ids and self.bank_partner_id.bank_ids[0]


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    debit_line = fields.Boolean()

    @api.onchange('name')
    def update_debit_line(self):
        for rec in self:
            if rec.product_id:
                rec.debit_line = True

    def _get_computed_account(self):

        self.ensure_one()
        self = self.with_context(force_company=self.move_id.journal_id.company_id.id)

        if not self.product_id:
            return

        fiscal_position = self.move_id.fiscal_position_id
        accounts = self.product_id.product_tmpl_id.get_product_accounts(fiscal_pos=fiscal_position)

        if self.move_id.is_sale_document(include_receipts=True):
            if self.move_id.is_debit_note:
                return accounts['receivable']
            else:
                return accounts['income'] or self.account_id
        elif self.move_id.is_purchase_document(include_receipts=True):
            # In invoice.
            return accounts['expense'] or self.account_id


    @api.depends('debit', 'credit', 'account_id', 'amount_currency', 'currency_id', 'matched_debit_ids',
                 'matched_credit_ids', 'matched_debit_ids.amount', 'matched_credit_ids.amount', 'move_id.state',
                 'company_id', 'partner_id')
    def _amount_residual(self):
        """ Computes the residual amount of a move line from a reconcilable account in the company currency and the line's currency.
            This amount will be 0 for fully reconciled lines or lines from a non-reconcilable account, the original line amount
            for unreconciled lines, and something in-between for partially reconciled lines.
        """
        for line in self:

            if line.account_id.reconcile and line.debit_line:
                line.reconciled = False
                line.amount_residual = 0
                line.amount_residual_currency = 0
                continue
            if not line.account_id.reconcile and line.account_id.internal_type != 'liquidity':
                line.reconciled = False
                line.amount_residual = 0
                line.amount_residual_currency = 0
                continue

            amount_residual_currency = abs(line.amount_currency) or 0.0
            sign = 1 if (line.debit - line.credit) > 0 else -1

            amount = abs(line.debit - line.credit)

            if not line.debit and not line.credit and line.amount_currency and line.currency_id:
                # residual for exchange rate entries
                sign = 1 if float_compare(line.amount_currency, 0,
                                          precision_rounding=line.currency_id.rounding) == 1 else -1

            for partial_line in (line.matched_debit_ids + line.matched_credit_ids):
                # If line is a credit (sign = -1) we:
                #  - subtract matched_debit_ids (partial_line.credit_move_id == line)
                #  - add matched_credit_ids (partial_line.credit_move_id != line)
                # If line is a debit (sign = 1), do the opposite.
                sign_partial_line = sign if partial_line.credit_move_id == line else (-1 * sign)

                amount += sign_partial_line * partial_line.amount

                # getting the date of the matched item to compute the amount_residual in currency
                if line.currency_id and line.amount_currency:
                    if partial_line.currency_id and partial_line.currency_id == line.currency_id:
                        amount_residual_currency += sign_partial_line * partial_line.amount_currency
                    else:
                        if line.balance and line.amount_currency:
                            rate = line.amount_currency / line.balance
                        else:
                            date = partial_line.credit_move_id.date if partial_line.debit_move_id == line else partial_line.debit_move_id.date
                            rate = line.currency_id.with_context(date=date).rate
                        amount_residual_currency += sign_partial_line * line.currency_id.round(
                            partial_line.amount * rate)

            # computing the `reconciled` field.
            reconciled = False
            digits_rounding_precision = line.move_id.company_id.currency_id.rounding
            if float_is_zero(amount, precision_rounding=digits_rounding_precision) and (
                    line.matched_debit_ids or line.matched_credit_ids):
                if line.currency_id and line.amount_currency:

                    if float_is_zero(amount_residual_currency, precision_rounding=line.currency_id.rounding):
                        reconciled = True
                else:
                    reconciled = True
            line.reconciled = reconciled

            line.amount_residual = line.move_id.company_id.currency_id.round(
                amount * sign) if line.move_id.company_id else amount * sign
            line.amount_residual_currency = line.currency_id and line.currency_id.round(
                amount_residual_currency * sign) or 0.0

    @api.onchange('asset_category_id')
    def onchange_asset_category_id(self):
        res = super(AccountMoveLine, self).onchange_asset_category_id()
        if self.move_id.type == 'in_invoice' and self.asset_category_id and self.move_id.is_mui_cip_transaction:
            self.account_id = self.asset_category_id.mui_cip_acc.id

        return res


