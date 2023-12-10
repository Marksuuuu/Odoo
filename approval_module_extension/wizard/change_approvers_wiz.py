# -*- coding: utf-8 -*-
import datetime
import hashlib
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from odoo import api, fields, models, _
from odoo.exceptions import UserError



class ChangeApproversWiz(models.TransientModel):
    _name = 'change.approvers.wiz'
    # _inherit = 'purchase.order'

    approver_id = fields.Many2one('hr.employee', string="Approver", domain=lambda self: self.get_approver_domain())
    department_id = fields.Many2one('account.analytic.account', string="Department", store=True)
    reason = fields.Many2one('change.approver.rsn', string="Reason for Change")
    date = fields.Date(string="Date of Change",
                       default=lambda self: self._context.get('date', fields.Date.context_today(self)))
    # state = fields.Selection(
    #     selection_add=[('to_approve', 'To Approve'), ('disapprove', 'Disapproved'), ('approved', 'Approved')])
    # approval_status = fields.Selection(selection=[
    #     ('po_approval', 'For Approval'),
    #     ('approved', 'Approved'),
    #     ('disapprove', 'Disapproved'),
    #     ('cancel', 'Cancelled')
    # ], string='Status')

    po_id = fields.Char()

    @api.onchange('department_id')
    def get_approver_domain(self):
        active_id = self._context.get('active_id')
        purchase_id = self.env['purchase.order'].browse(active_id)
        for rec in purchase_id:
            domain = []
            if rec.state in ('draft', 'sent', 'to_approve'):
                res = self.env["department.approvers"].search(
                    [("dept_name", "=", rec.department_id.id), ("approval_type.name", '=', 'Purchase Orders')])
            else:
                res = self.env["department.approvers"].search(
                    [("dept_name", "=", rec.department_id.id), ("approval_type.name", '=', 'Purchase Requests')])

            if rec.department_id and rec.approval_stage == 1:
                approver_dept = [x.first_approver.id for x in res.set_first_approvers]
                rec.approver_id = approver_dept[0]
                domain.append(('id', '=', approver_dept))

            elif rec.department_id and rec.approval_stage == 2:
                approver_dept = [x.second_approver.id for x in res.set_second_approvers]
                rec.approver_id = approver_dept[0]
                domain.append(('id', '=', approver_dept))

            elif rec.department_id and rec.approval_stage == 3:
                approver_dept = [x.third_approver.id for x in res.set_third_approvers]
                rec.approver_id = approver_dept[0]
                domain.append(('id', '=', approver_dept))

            elif rec.department_id and rec.approval_stage == 4:
                approver_dept = [x.fourth_approver.id for x in res.set_fourth_approvers]
                rec.approver_id = approver_dept[0]
                domain.append(('id', '=', approver_dept))

            elif rec.department_id and rec.approval_stage == 5:
                approver_dept = [x.fifth_approver.id for x in res.set_fifth_approvers]
                rec.approver_id = approver_dept[0]
                domain.append(('id', '=', approver_dept))

            else:
                domain = []

            return {'domain': {'approver_id': domain}}

    def button_submit(self):
        active_id = self._context.get('active_id')
        purchase_id = self.env['purchase.order'].browse(active_id)
        approval_type = self.env["purchase.approval.types"].search([("name", '=', 'Purchase Orders')])

        self.po_name = purchase_id.name
        self.po_id = active_id

        vals = {
            'approver_id': self.approver_id.id,
        }

        purchase_id.write(vals)

        history = self.env['change.approver.rsn'].create({
            'name': self.reason.name,
            'approval_type': approval_type.id,
            'date': self.date
        })
        self.submit_to_new_approver()


    def generate_token(self):
        active_id = self._context.get('active_id')
        purchase_id = self.env['purchase.order'].browse(active_id)
        self.po_name = purchase_id.name
        self.po_id = active_id

        now = datetime.datetime.now()
        token = "{}-{}-{}-{}".format(self.po_id, self.po_name, self.env.user.id, now)
        return hashlib.sha256(token.encode()).hexdigest()


    def approval_dashboard_link(self):
        # Approval Dashboard Link Section
        approval_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        approval_action = self.env['ir.actions.act_window'].search([('name', '=', 'Purchase Order Approval Dashboard')], limit=1)
        action_id = approval_action.id
        odoo_params = {
            "action": action_id,
        }

        query_string = '&'.join([f'{key}={value}' for key, value in odoo_params.items()])
        list_view_url = f"{approval_base_url}/web?debug=0#{query_string}"

        return list_view_url

    def generate_odoo_link(self):
        action = self.env['ir.actions.act_window'].search([('res_model', '=', 'purchase.order')], limit=1)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        result = re.sub(r'\((.*?)\)', '', str(action)).replace(',', '')
        res = f"{result},{action.id}"
        result = re.sub(r'\s*,\s*', ',', res)

        menu = self.env['ir.ui.menu'].search([('action', '=', result)], limit=1)

        params = {
            "id": self.po_id,
            "action": action.id,
            "model": "purchase.order",
            "view_type": "form",
            "cids": 1,
            "menu_id": menu.id
        }

        query_params = "&".join(f"{key}={value}" for key, value in params.items())
        po_form_link = f"{base_url}/web#{query_params}"


        return po_form_link
    def submit_to_new_approver(self):
        # Approval Dashboard Link Section
        approval_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        approval_action = self.env['ir.actions.act_window'].search([('name', '=', 'Purchase Order Approval Dashboard')], limit=1)
        action_id = approval_action.id
        odoo_params = {
            "action": action_id,
        }

        query_string = '&'.join([f'{key}={value}' for key, value in odoo_params.items()])
        approval_list_view_url = f"{approval_base_url}/web?debug=0#{query_string}"

        # Generate Odoo Link Section
        odoo_action = self.env['ir.actions.act_window'].search([('res_model', '=', 'purchase.order')], limit=1)
        odoo_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        odoo_result = re.sub(r'\((.*?)\)', '', str(odoo_action)).replace(',', '')
        odoo_res = f"{odoo_result},{odoo_action.id}"
        odoo_result = re.sub(r'\s*,\s*', ',', odoo_res)

        odoo_menu = self.env['ir.ui.menu'].search([('action', '=', odoo_result)], limit=1)
        odoo_params = {
            "id": self.po_id,
            "action": odoo_action.id,
            "model": "purchase.order",
            "view_type": "form",
            "cids": 1,
            "menu_id": odoo_menu.id
        }
        odoo_query_params = "&".join(f"{key}={value}" for key, value in odoo_params.items())
        po_form_link = f"{odoo_base_url}/web#{odoo_query_params}"

        self.generate_odoo_link()
        self.approval_dashboard_link()

        fetch_getEmailReceiver = self.approver_id.work_email  # self.approver_id.work_email DEFAULT RECEIVER CHANGE IT TO IF YOU WANT ----> IF YOU WANT TO SET AS DEFAULT OR ONLY ONE ##
        self.sending_email_to_next_approver(fetch_getEmailReceiver, po_form_link, approval_list_view_url)

        # self.write({
        #     'approval_status': 'po_approval',
        #     'state': 'to_approve',
        #     'to_approve': True,
        #     'show_submit_request': False
        # })

    def sending_email_to_next_approver(self, fetch_getEmailReceiver, po_form_link, approval_list_view_url):
        sender = 'noreply@teamglac.com'
        host = "192.168.1.114"
        port = 25
        username = "noreply@teamglac.com"
        password = "noreply"

        active_id = self._context.get('active_id')
        purchase_id = self.env['purchase.order'].browse(active_id)

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        token = self.generate_token()

        approval_url = "{}/purchase_order/request/approve/{}".format(base_url, token)
        disapproval_url = "{}/purchase_order/request/disapprove/{}".format(base_url, token)

        self._cr.execute("""
                   UPDATE purchase_order SET approval_link = %s WHERE id = %s
               """, (token, active_id))

        msg = MIMEMultipart()
        msg['From'] = formataddr(('Odoo Mailer', sender))
        msg['To'] = fetch_getEmailReceiver
        msg['Subject'] = 'Purchase Order For Approval [' + self.po_name + ']'

        html_content = """
            <html>
            <head>
                <style>
                    table {
                        border-collapse: collapse;
                        width: 100%;
                    }

                    th, td {
                        border: 1px solid black;
                        padding: 8px;
                        text-align: left;
                    }

                    th {
                        background-color: #dddddd;
                    }

                </style>
            </head>
            <body>"""

        html_content += f"""
            <dt><b>{self.po_name}</b></dt>
                <br></br>
                    <dd>Purchase Representative: &nbsp;&nbsp;{purchase_id.user_id.name if purchase_id.user_id.name != False else ""}</dd>
                    <dd>Confirmation Date: &nbsp;&nbsp;{purchase_id.date_approve if purchase_id.date_approve != False else ""}</dd>
                    <dd>Vendor: &nbsp;&nbsp;{purchase_id.partner_id.name if purchase_id.partner_id.name != False else ""}</dd>
                    <dd>Currency: &nbsp;&nbsp;{purchase_id.currency_id.name if purchase_id.currency_id.name != False else ""}</dd>
                    <dd>Source Document: &nbsp;&nbsp;{purchase_id.origin if purchase_id.origin != False else ""}</dd>
                <br></br>
                    <span><b>ITEMS REQUESTED</b></span>
                <br></br>
            """

        html_content += """
            <br></br>
            <table>
                        <tr>
                            <th>Product</th>
                            <th>Description</th>
                            <th>Scheduled Date</th>
                            <th>Analytic Account</th>
                            <th>Quantity</th>
                            <th>Received</th>
                            <th>UoM</th>
                            <th>Unit Price</th>
                            <th>Taxes</th>
                            <th>Subtotal</th>
                        </tr>
                        """

        for line in purchase_id.order_line:
            html_content += f"""
                        <tr>
                            <td>{line.product_id.name if line.product_id.name != False else ""}</td>
                            <td>{line.name if line.name != False else ""}</td>
                            <td>{line.date_planned if line.date_planned != False else ""}</td>
                            <td>{line.account_analytic_id.name if line.account_analytic_id.name != False else ""}</td>
                            <td>{line.product_qty if line.product_qty != False else ""}</td>
                            <td>{line.qty_received if line.qty_received != False else ""}</td>
                            <td>{line.product_uom.name if line.product_uom.name != False else ""}</td>
                            <td>{'{:,.2f}'.format(line.price_unit) if line.price_unit != False else ""}</td>
                            <td>{line.taxes_id.name if line.taxes_id.name != False else ""}</td>
                            <td>{'{:,.2f}'.format(line.price_subtotal)}&nbsp;{line.currency_id.name if line.currency_id.name != False else ""}</td>
                        </tr>
            """

        html_content += f"""
                </table>

                </body>
                <br></br>
                <br></br>
                <br></br>
                <span style="font-style: italic;";><a href="{approval_url}"  style="color: green;">APPROVE</a> / <a href="{disapproval_url}"  style="color: red;">DISAPPROVE</a> / <a href="{po_form_link}"  style="color: blue;">ODOO PO FORM
                </a> / <a href="{approval_list_view_url}">ODOO APPROVAL DASHBOARD</a></span>

                </html>
            """

        msg.attach(MIMEText(html_content, 'html'))

        try:
            smtpObj = smtplib.SMTP(host, port)
            smtpObj.login(username, password)
            smtpObj.sendmail(sender, fetch_getEmailReceiver, msg.as_string())

            msg = "Successfully sent email"
            return {
                'success': {
                    'title': 'Successfully email sent!',
                    'message': f'{msg}'}
            }
        except Exception as e:
            msg = f"Error: Unable to send email: {str(e)}"
            return {
                'warning': {
                    'title': 'Error: Unable to send email!',
                    'message': f'{msg}'}
            }
