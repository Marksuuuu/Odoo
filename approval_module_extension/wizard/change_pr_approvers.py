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


class ChangePRApprovers(models.TransientModel):
    _name = 'change.pr.approvers'
    _inherit = 'purchase.requisition'

    approver_id = fields.Many2one('hr.employee', string="Approver", domain=lambda self: self.get_approver_domain())
    department_id = fields.Many2one('account.analytic.account', string="Department", store=True)
    reason = fields.Many2one('change.approver.rsn', string="Reason for Change")
    date = fields.Date(string="Date of Change",
                       default=lambda self: self._context.get('date', fields.Date.context_today(self)))

    pr_id = fields.Char()

    @api.onchange('department_id')
    def get_approver_domain(self):
        active_id = self._context.get('active_id')
        purchase_id = self.env['purchase.requisition'].browse(active_id)
        for rec in purchase_id:
            domain = []
            res = self.env["department.approvers"].search(
                [("dept_name", "=", rec.department_id.id), ("approval_type.name", '=', 'Purchase Orders')])

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
        purchase_id = self.env['purchase.requisition'].browse(active_id)
        approval_type = self.env["purchase.approval.types"].search([("name", '=', 'Purchase Requests')])
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


    # this retrieves the current date, formats it as day-month-year, and assigns the formatted date
    def getCurrentDate(self):
        date_now = datetime.datetime.now()
        formatted_date = date_now.strftime("%m/%d/%Y")

        self.date_today = formatted_date

        if self.initial_approver_name:
            self.initial_approval_date = formatted_date

        if hasattr(self, 'second_approver_name') and self.second_approver_name:
            self.second_approval_date = formatted_date

        if hasattr(self, 'third_approver_name') and self.third_approver_name:
            self.third_approval_date = formatted_date

        if hasattr(self, 'fourth_approver_name') and self.fourth_approver_name:
            self.fourth_approval_date = formatted_date

        if hasattr(self, 'final_approver_name') and self.final_approver_name:
            self.final_approval_date = formatted_date


    def approval_dashboard_link(self):
        # Approval Dashboard Link Section
        approval_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        approval_action = self.env['ir.actions.act_window'].search(
            [('name', '=', 'Purchase Request Approval Dashboard')], limit=1)
        action_id = approval_action.id

        odoo_params = {
            "action": action_id,
        }

        query_string = '&'.join([f'{key}={value}' for key, value in odoo_params.items()])
        list_view_url = f"{approval_base_url}/web?debug=0#{query_string}"
        return list_view_url


    def generate_odoo_link(self):
        # Generate Odoo Link Section
        action = self.env['ir.actions.act_window'].search([('res_model', '=', 'purchase.requisition')], limit=1)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        result = re.sub(r'\((.*?)\)', '', str(action)).replace(',', '')
        res = f"{result},{action.id}"
        result = re.sub(r'\s*,\s*', ',', res)

        menu = self.env['ir.ui.menu'].search([('action', '=', result)], limit=1)
        params = {
            "id": self.pr_id,
            "action": action.id,
            "model": "purchase.requisition",
            "view_type": "form",
            "cids": 1,
            "menu_id": menu.id
        }
        query_params = "&".join(f"{key}={value}" for key, value in params.items())
        pr_form_link = f"{base_url}/web#{query_params}"
        return pr_form_link


    def generate_token(self):
        active_id = self._context.get('active_id')
        purchase_id = self.env['purchase.requisition'].browse(active_id)
        self.pr_name = purchase_id.name
        self.pr_id = active_id

        now = datetime.datetime.now()
        token = "{}-{}-{}-{}".format(self.pr_id, self.pr_name, self.env.user.id, now)

        return hashlib.sha256(token.encode()).hexdigest()


    # Next Approver Sending of Email
    def submit_to_new_approver(self):
        # Approval Dashboard Link Section
        active_id = self._context.get('active_id')
        purchase_id = self.env['purchase.requisition'].browse(active_id)
        self.pr_name = purchase_id.name
        self.pr_id = active_id

        approval_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        approval_action = self.env['ir.actions.act_window'].search(
            [('name', '=', 'Purchase Request Approval Dashboard')], limit=1)
        action_id = approval_action.id
        odoo_params = {
            "action": action_id,
        }

        query_string = '&'.join([f'{key}={value}' for key, value in odoo_params.items()])
        approval_list_view_url = f"{approval_base_url}/web?debug=0#{query_string}"

        # Generate Odoo Link Section
        odoo_action = self.env['ir.actions.act_window'].search([('res_model', '=', 'purchase.requisition')], limit=1)
        odoo_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        odoo_result = re.sub(r'\((.*?)\)', '', str(odoo_action)).replace(',', '')
        odoo_res = f"{odoo_result},{odoo_action.id}"
        odoo_result = re.sub(r'\s*,\s*', ',', odoo_res)

        odoo_menu = self.env['ir.ui.menu'].search([('action', '=', odoo_result)], limit=1)
        odoo_params = {
            "id": self.pr_id,
            "action": odoo_action.id,
            "model": "purchase.requisition",
            "view_type": "form",
            "cids": 1,
            "menu_id": odoo_menu.id
        }
        odoo_query_params = "&".join(f"{key}={value}" for key, value in odoo_params.items())
        pr_form_link = f"{odoo_base_url}/web#{odoo_query_params}"

        self.generate_odoo_link()
        self.approval_dashboard_link()

        fetch_getEmailReceiver = self.approver_id.work_email

        self.sending_email_to_next_approver(fetch_getEmailReceiver, pr_form_link, approval_list_view_url)

        self.write({
            'approval_status': 'pr_approval',
            'state': 'to_approve',
            'to_approve': True,
            'show_submit_request': False
        })


    def sending_email_to_next_approver(self, fetch_getEmailReceiver, pr_form_link, approval_list_view_url):
        sender = 'noreply@teamglac.com'
        host = "192.168.1.114"
        port = 25
        username = "noreply@teamglac.com"
        password = "noreply"

        active_id = self._context.get('active_id')
        purchase_id = self.env['purchase.requisition'].browse(active_id)
        self.pr_name = purchase_id.name
        self.pr_id = active_id

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        token = self.generate_token()

        approval_url = "{}/purchase_requisition/request/approve/{}".format(base_url, token)
        disapproval_url = "{}/purchase_requisition/request/disapprove/{}".format(base_url, token)

        self._cr.execute("""
                UPDATE purchase_requisition SET approval_link = %s WHERE id = %s
            """, (token, active_id))

        msg = MIMEMultipart()
        msg['From'] = formataddr(('Odoo Mailer', sender))
        msg['To'] = fetch_getEmailReceiver
        msg['Subject'] = 'Purchase Request For Approval [' + self.pr_name + ']'
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
               <dt><b>{self.pr_name}</b></dt>
                   <br></br>
                       <dd>Requested by: &nbsp;&nbsp;{purchase_id.user_id.name if purchase_id.user_id.name != False else ""}</dd>
                       <dd>Date Requested: &nbsp;&nbsp;{purchase_id.ordering_date if purchase_id.ordering_date != False else ""}</dd>
                       <dd>Vendor: &nbsp;&nbsp;{purchase_id.vendor_id.name if purchase_id.vendor_id.name != False else ""}</dd>
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
                               <th>Quantity</th>
                               <th>Ordered Quantities</th>
                               <th>UoM</th>
                               <th>Scheduled Date</th>
                               <th>Unit Price</th>
                               <th>Subtotal</th>
                           </tr>
                           """

        for line in purchase_id.line_ids:
            html_content += f"""
                           <tr>
                               <td>{line.product_id.name}</td>
                               <td>{line.product_qty}</td>
                               <td>{line.qty_ordered}</td>
                               <td>{line.product_uom_id.name}</td>
                               <td>{line.schedule_date if line.schedule_date != False else ""}</td>
                               <td>{'{:,.2f}'.format(line.price_unit)}</td>
                               <td>{'{:,.2f}'.format(line.subtotal)}</td>
                           </tr>
               """

        html_content += f"""
                   </table>
                   <br></br>
                       <span><b>JUSTIFICATION</b></span>
                       <dd style="width: 100%; white-space: pre-wrap;">{self.justification if self.justification != False else ""}</dd>
                   </body>
                   <br></br>
                   <br></br>
                   <br></br>
                   <span style="font-style: italic;";><a href="{approval_url}"  style="color: green;">APPROVE</a> / <a href="{disapproval_url}"  style="color: red;">DISAPPROVE</a> / <a href="{pr_form_link}"  style="color: blue;">ODOO PR FORM
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

