from odoo import fields, models, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    tpc_dm_cm_connection = fields.Many2one('tpc.dm.cm.request', string='Tpc Dm Cm Connection')


