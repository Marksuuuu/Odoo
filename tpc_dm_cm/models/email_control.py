from odoo import fields, models


class EmailControl(models.Model):
    _name = 'email.control'
    _description = 'Team Pacific Corporation DM CM'

    name = fields.Many2one('res.users', string='Employee')
    email = fields.Char(related='name.login', string='Email', readonly=True)
    group = fields.Many2one('account.analytic.account', string='Group')
    status = fields.Selection([('active', 'ACTIVE'), ('inactive', 'INACTIVE')], string='Status')
    cc = fields.Boolean(string='CC')
    bcc = fields.Boolean(string='BCC')


class SourceTradeNonTrade(models.Model):
    _name = 'source.trade.non.trade'
    _description = 'Team Pacific Corporation DM CM'
    _rec_name = 'source_trade_n_trade'

    source_ar_lines = fields.One2many('source.trade.non.trade.line', 'ar_conn')
    source_sales_lines = fields.One2many('source.sales.line', 'sales_conn')
    source_trade_n_trade = fields.Char(string='Trade or Non Trade')


class SourceTradeNonTradeLine(models.Model):
    _name = 'source.trade.non.trade.line'
    _description = 'Team Pacific Corporation DM CM'

    ar_conn = fields.Many2one('source.trade.non.trade')
    name = fields.Many2one('res.users', string='Employee')
    email = fields.Char(related='name.login', string='Email', readonly=True)


class SourceSalesLine(models.Model):
    _name = 'source.sales.line'
    _description = 'Team Pacific Corporation DM CM'

    sales_conn = fields.Many2one('source.trade.non.trade')
    name = fields.Many2one('res.users', string='Employee')
    email = fields.Char(related='name.login', string='Email', readonly=True)
