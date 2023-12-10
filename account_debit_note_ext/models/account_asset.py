# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from itertools import groupby
from odoo.exceptions import RedirectWarning, UserError, ValidationError, AccessError


class AccountAssetAsset(models.Model):
    _inherit = 'account.asset.asset'

    invoice_ids = fields.Many2many('account.move', string='Invoice',
                                 states={'draft': [('readonly', False)]},
                                 copy=False)

    ppa_reference = fields.Char(string="PPA reference")
