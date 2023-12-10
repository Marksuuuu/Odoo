from odoo import fields, models, api, _
from odoo.exceptions import UserError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    debit_sequence = fields.Boolean(string='Dedicated Debit Note Sequence',
                                    help="Check this box if you don't want to share the same sequence for invoices and debit notes made from this journal",
                                    default=True)
    debit_sequence_number_next = fields.Integer(string='Debit Notes Next Number',
                                                help='The next sequence number will be used for the next debit note.',
                                                compute='_compute_debit_seq_number_next',
                                                inverse='_inverse_debit_seq_number_next')

    debit_sequence_id = fields.Many2one('ir.sequence', string='Debit Note Entry Sequence',
                                        help="This field contains the information related to the numbering of the debit note entries of this journal.",
                                        copy=False)


    def _inverse_debit_seq_number_next(self):
        '''Inverse 'debit_sequence_number_next' to edit the current sequence next number.
        '''
        for journal in self:
            if journal.debit_sequence_id and journal.debit_sequence and journal.debit_sequence_number_next:
                sequence = journal.debit_sequence_id._get_current_sequence()
                sequence.sudo().number_next = journal.debit_sequence_number_next

    @api.depends('debit_sequence_id.use_date_range', 'debit_sequence_id.number_next_actual')
    def _compute_debit_seq_number_next(self):
        '''Compute 'sequence_number_next' according to the current sequence in use,
        an ir.sequence or an ir.sequence.date_range.
        '''
        for journal in self:
            if journal.debit_sequence_id and journal.debit_sequence:
                sequence = journal.debit_sequence_id._get_current_sequence()
                journal.debit_sequence_number_next = sequence.number_next_actual
            else:
                journal.debit_sequence_number_next = 1

    def write(self, vals):
        result = super(AccountJournal, self).write(vals)
        for journal in self:
            if journal.debit_sequence and journal.type in ('sale', 'purchase'):
                if journal.debit_sequence_id:
                    if 'code' in vals and journal.code != vals['code']:
                        new_prefix = self._get_sequence_prefix(vals['code'], debit=True)
                        journal.refund_sequence_id.write({'prefix': new_prefix})
                else:
                    journal_vals = {
                        'name': journal.name,
                        'company_id': journal.company_id.id,
                        'code': journal.code,
                        'debit_sequence_number_next': vals.get('debit_sequence_number_next',
                                                               journal.debit_sequence_number_next),
                    }
                    journal.debit_sequence_id = self.sudo()._create_sequence(journal_vals, debit=True).id

        return result

    @api.model
    def _get_sequence_prefix(self, code, refund=False, debit=False):
        prefix = code.upper()
        if debit:
            prefix = 'D' + prefix
            return prefix + '/%(range_year)s/'
        else:
            return super(AccountJournal, self)._get_sequence_prefix(code, refund=refund)

    @api.model
    def _create_sequence(self, vals, refund=False, debit=False):
        """ Create new no_gap entry sequence for every new Journal"""

        if debit:
            prefix = self._get_sequence_prefix(vals['code'], refund, debit)

            seq_name = debit and vals['code'] + _(': Debit') or vals['code']
            seq = {
                'name': _('{} Sequence').format(seq_name),
                'implementation': 'no_gap',
                'prefix': prefix,
                'padding': 4,
                'number_increment': 1,
                'use_date_range': True,
            }
            if 'company_id' in vals:
                seq['company_id'] = vals['company_id']
            seq = self.env['ir.sequence'].create(seq)
            seq_date_range = seq._get_current_sequence()
            seq_date_range.number_next = debit and vals.get('debit_sequence_number_next', 1) or vals.get(
                'sequence_number_next', 1)
            return seq
        else:
            return super(AccountJournal, self)._create_sequence(vals, refund=refund)

    @api.model
    def create(self, vals):

        if 'debit_sequence' not in vals:
            vals['debit_sequence'] = vals['type'] in ('sale', 'purchase')
        # We just need to create the relevant sequences according to the chosen options
        if not vals.get('debit_sequence_id'):
            vals.update({'debit_sequence_id': self.sudo()._create_sequence(vals).id})
        if vals.get('type') in ('sale', 'purchase') and vals.get('debit_sequence') and not vals.get(
                'debit_sequence_id'):
            vals.update({'debit_sequence_id': self.sudo()._create_sequence(vals, refund=True).id})

        journal = super(AccountJournal, self.with_context(mail_create_nolog=True)).create(vals)
        return journal