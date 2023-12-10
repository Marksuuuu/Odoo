import base64
import datetime
import hashlib
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class TpcDmCmRequest(models.Model):
    _name = 'tpc.dm.cm.request'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'Team Pacific Corporation DM CM'

    name = fields.Char(string='Serial No.', required=True, copy=False, readonly=True, index=True,
                       default=lambda self: _('New'))
    user_id = fields.Many2one('res.users', string='Requesters', copy=False, required=True)
    department = fields.Char(related='user_id.login', string="Requesters Department", stored=True, readonly=True)
    po_reference = fields.Char(string='Po Reference', required=True)
    ordering_date = fields.Datetime(
        string='Invoice Date',
        default=lambda self: fields.Datetime.now(),
        help='This field will have the current date and time as the default value.'
    )
    particulars = fields.Many2one('tpc.dm.cm.particulars', string='Particulars', required=True)
    dm_cm_line = fields.One2many('tpc.dm.cm.request.line', 'dm_cm')
    dm_cm_email = fields.One2many('tpc.dm.cm.request.email', 'dm_cm_email')
    source = fields.Many2one('source.trade.non.trade', required=True)
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('to_approve', 'To Approve'), ('approved', 'Approved'),
                   ('disapprove', 'Disapproved'), ('cancel', 'Cancelled')], default='draft')
    state_blanket_order = fields.Selection([('draft', 'Draft'), ('to_approve', 'To Approve'), ('approved', 'Approved'),
                                            ('disapprove', 'Disapproved'), ('cancel', 'Cancelled')], default='draft')
    approval_status = fields.Selection(selection=[
        ('pr_approval', 'For Approval'),
        ('approved', 'Approved'),
        ('disapprove', 'Disapproved'),
        ('cancel', 'Cancelled')
    ], string='Status')
    approver_id = fields.Many2one('hr.employee', string="Approver", required=True,
                                  domain=lambda self: self.get_approver_domain())
    approval_stage = fields.Integer(default=1)
    department_id = fields.Many2one('account.analytic.account', string="Approvers Department", required=True,
                                    store=True)
    to_approve = fields.Boolean()
    to_approve_po = fields.Boolean()
    show_submit_request = fields.Boolean()
    disapproval_reason = fields.Char(string="Reason for Disapproval")
    # show_request = fields.Char()
    approval_type_id = fields.Many2one('purchase.approval.types')
    approval_id = fields.Many2one('purchase.approval')
    is_approver = fields.Boolean(compute="compute_approver")

    # New fields
    initial_approver_name = fields.Char()
    second_approver_name = fields.Char()
    third_approver_name = fields.Char()
    fourth_approver_name = fields.Char()
    final_approver_name = fields.Char()

    approval_link = fields.Char('Approval link')
    check_status = fields.Char(compute='compute_check_status', store=True)
    approver_count = fields.Integer(compute='_compute_approver_count', store=True)
    date_today = fields.Char()

    initial_approver_job_title = fields.Char(compute='get_approver_title', store=True)
    second_approver_job_title = fields.Char(compute='get_approver_title', store=True)
    third_approver_job_title = fields.Char(compute='get_approver_title', store=True)
    fourth_approver_job_title = fields.Char(compute='get_approver_title', store=True)
    final_approver_job_title = fields.Char(compute='get_approver_title', store=True)

    initial_approver_email = fields.Char()
    second_approver_email = fields.Char()
    third_approver_email = fields.Char()
    fourth_approver_email = fields.Char()
    final_approver_email = fields.Char()

    initial_approval_date = fields.Char()
    second_approval_date = fields.Char()
    third_approval_date = fields.Char()
    fourth_approval_date = fields.Char()
    final_approval_date = fields.Char()

    purchase_rep_email = fields.Char(related="user_id.login", store=True)
    trade_final_approver = fields.Many2one('res.users', string='Final Approver')
    dm_cm_number = fields.Char(string='DM/CM No.')
    dm_cm_select = fields.Selection([('dm', 'DM'), ('cm', 'CM')])
    is_field_visible = fields.Boolean(string='Is Field Visible', compute='_compute_is_field_visible')

    _trade_final_approver_date_approver = fields.Date(string='Date Approver by Final Approver')

    # Boolean Fields

    submit_for_approval_bool = fields.Boolean(string='submit for approval', default=True)
    submit_for_approve_bool = fields.Boolean(string='submit for approval', default=True)
    debit_memo_request_final_submit = fields.Boolean(string='Debit Memo Request', default=True)
    credit_memo_request_final_submit = fields.Boolean(string='Debit Memo Request', default=True)
    debit_note = fields.Many2one('account.move', string='Debit Note Connection', readonly=True)
    credit_note = fields.Many2one('account.move', string='Debit Note Connection', readonly=True)
    _trade_final_approver = fields.Boolean(string='Trade Final Approver', default=False)

    # Counter

    flag = fields.Boolean(string='Counter for Redundant Email', default=True)

    sales_or_ar = fields.Char(string='Counter')

    # _calculate_cost = fields.Integer(calculate='_calculate')

    def confirm(self):
        self.state = 'to_approve'

    # @api.model
    def cc_bcc(self):
        return self.env['tpc.dm.cm.request.email'].search([('dm_cm_email', '=', self.id)])

    def checking_self(self):
        pass

    def my_function(self):
        # Use a list for emails
        emails = [
            self.initial_approver_email,
            self.second_approver_email,
            self.third_approver_email,
            self.fourth_approver_email,
            self.final_approver_email,
            self.purchase_rep_email,
        ]

        # Simplify email retrieval using a loop
        email_list = [email if email else "" for email in emails]

        # Check if the flag is True
        if self.flag:
            # Create empty lists to store email addresses

            # Check for email addresses based on the source condition
            if self.source.source_trade_n_trade == 'Trade':
                email_list_ar = []
                for rec in self.source.source_ar_lines:
                    if rec.email:
                        email_list_ar.append(rec.email)
                        print('iam going in trade')

            elif self.source.source_trade_n_trade == 'Non-Trade':
                email_list_sales = []
                email_list_ar = []
                if not self.sales_or_ar:
                    for rec in self.source.source_ar_lines:
                        if rec.email:
                            email_list_ar.append(rec.email)
                            print('iam going in ar')
                            self.write({
                                'sales_or_ar': 'SALES'
                            })
                elif self.sales_or_ar == 'SALES':
                    for rec in self.source.source_sales_lines:
                        if rec.email:
                            email_list_sales.append(rec.email)
                            print('iam going to sales')


        else:
            # Call the send_to_final_approver_email function with the appropriate email list
            self.send_to_final_approver_email(email_list)

    def get_all_email_attached(self):

        email_list = []

        if self.source.source_trade_n_trade in ['Trade', 'Non-Trade']:
            email_list.extend(rec.email for rec in self.source.source_ar_lines)

        emails = [
            self.initial_approver_email,
            self.second_approver_email,
            self.third_approver_email,
            self.fourth_approver_email,
            self.final_approver_email,
            self.purchase_rep_email,
        ]

        full_mail_list = [email if email else "" for email in emails]

        email_list.extend(full_mail_list)

        print(email_list)
        return email_list

    def _calculate(self):
        pass

    def method_direct_trigger(self):
        print('test')

    def cancel_function(self):
        self.write({
            'state': 'cancel',
            'approval_status': 'cancel'
        })

    def test_if_no_data(self):
        if not self.dm_cm_line:
            print('no data')
        else:
            print(self.dm_cm_line.customer.name, 'customer')
            print('have')

    def _compute_is_field_visible(self):
        for record in self:
            source_trade_non_trade_model = self.env['source.trade.non.trade']
            records = source_trade_non_trade_model.search([])
            current_user = self.env.user
            print(current_user)
            is_visible = False
            for rec in records:
                print(rec.source_ar_lines.name)
                if current_user == rec.source_ar_lines.name:
                    print(current_user, 'current')
                    is_visible = True
                    break

            record.is_field_visible = is_visible

    @api.onchange('dm_cm_line')
    def _onchange_one2many_field(self):
        if not self.dm_cm_line:
            raise UserError("Please note that data must be provided in the required fields to proceed.")

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('your.sequence.code') or '/'

        record = super(TpcDmCmRequest, self).create(vals)
        record._onchange_one2many_field()

        return record

    def write(self, values):
        res = super(TpcDmCmRequest, self).write(values)
        self._onchange_one2many_field()
        return res

    @api.depends('approval_status', 'state')
    def get_approvers_email(self):
        print('go to get approvers email')
        """
        Retrieves the email addresses of the relevant approvers based on approval status and state.

        Side Effects:
            Updates the email fields of the instance with the appropriate approver emails.
        """
        for rec in self:
            if rec.approval_status == 'approved' or rec.state == 'approved':
                if rec.initial_approver_name:
                    approver = self.env['hr.employee'].search([('name', '=', rec.initial_approver_name)],
                                                              limit=1)
                    rec.initial_approver_email = approver.work_email if approver else False

                if rec.second_approver_name:
                    approver = self.env['hr.employee'].search([('name', '=', rec.second_approver_name)], limit=1)
                    rec.second_approver_email = approver.work_email if approver else False

                if rec.third_approver_name:
                    approver = self.env['hr.employee'].search([('name', '=', rec.third_approver_name)], limit=1)
                    rec.third_approver_email = approver.work_email if approver else False

                if rec.fourth_approver_name:
                    approver = self.env['hr.employee'].search([('name', '=', rec.fourth_approver_name)], limit=1)
                    rec.fourth_approver_email = approver.work_email if approver else False

                if rec.final_approver_name:
                    approver = self.env['hr.employee'].search([('name', '=', rec.final_approver_name)], limit=1)
                    rec.final_approver_email = approver.work_email if approver else False

                rec.purchase_rep_email = self.purchase_rep_email

            elif rec.approval_status == 'disapprove' or rec.state == 'disapprove':
                res = self.env["department.approvers"].search(
                    [("dept_name", "=", rec.department_id.id), ("approval_type.name", '=', 'DM CM')])

                initial_approver_email = False
                second_approver_email = False
                third_approver_email = False
                fourth_approver_email = False
                final_approver_email = False

                if rec.department_id and res.set_first_approvers:
                    initial_approver_email = res.set_first_approvers[0].first_approver.work_email

                if rec.department_id and res.set_second_approvers:
                    second_approver_email = res.set_second_approvers[0].second_approver.work_email

                if rec.department_id and res.set_third_approvers:
                    third_approver_email = res.set_third_approvers[0].third_approver.work_email

                if rec.department_id and res.set_fourth_approvers:
                    fourth_approver_email = res.set_fourth_approvers[0].fourth_approver.work_email

                if rec.department_id and res.set_fifth_approvers:
                    final_approver_email = res.set_fifth_approvers[0].fifth_approver.work_email

                rec.initial_approver_email = initial_approver_email
                rec.second_approver_email = second_approver_email
                rec.third_approver_email = third_approver_email
                rec.fourth_approver_email = fourth_approver_email
                rec.final_approver_email = final_approver_email

                rec.purchase_rep_email = self.purchase_rep_email

    @api.depends('initial_approver_name', 'second_approver_name', 'third_approver_name', 'fourth_approver_name',
                 'final_approver_name')
    def get_approver_title(self):
        """
           Fetches the job title of the specified approvers.

           This method iterates over each record and searches for the specified approvers by their names.
           If an approver is found, the corresponding job title and work email are assigned to the record's fields.

        """
        for record in self:
            if record.initial_approver_name:
                approver = self.env['hr.employee'].search([('name', '=', record.initial_approver_name)], limit=1)
                record.initial_approver_job_title = approver.job_title if approver else False

            if record.second_approver_name:
                approver = self.env['hr.employee'].search([('name', '=', record.second_approver_name)], limit=1)
                record.second_approver_job_title = approver.job_title if approver else False

            if record.third_approver_name:
                approver = self.env['hr.employee'].search([('name', '=', record.third_approver_name)], limit=1)
                record.third_approver_job_title = approver.job_title if approver else False

            if record.fourth_approver_name:
                approver = self.env['hr.employee'].search([('name', '=', record.fourth_approver_name)], limit=1)
                record.fourth_approver_job_title = approver.job_title if approver else False

            if record.final_approver_name:
                approver = self.env['hr.employee'].search([('name', '=', record.final_approver_name)], limit=1)
                record.final_approver_job_title = approver.job_title if approver else False

    # this retrieves the current date, formats it as day-month-year, and assigns the formatted date
    def get_current_date(self):
        date_now = datetime.datetime.now()
        formatted_date = date_now.strftime("%m/%d/%Y")
        print(formatted_date, 'formatted date')
        self.date_today = formatted_date

        print(self.initial_approver_name)
        if self.initial_approver_name:
            self.initial_approval_date = formatted_date
            print(self.initial_approver_name)

        if hasattr(self, 'second_approver_name') and self.second_approver_name:
            self.second_approval_date = formatted_date

        if hasattr(self, 'third_approver_name') and self.third_approver_name:
            self.third_approval_date = formatted_date

        if hasattr(self, 'fourth_approver_name') and self.fourth_approver_name:
            self.fourth_approval_date = formatted_date

        if hasattr(self, 'final_approver_name') and self.final_approver_name:
            self.final_approval_date = formatted_date

    @api.depends('department_id')
    def _compute_approver_count(self):
        """
            Computes the total number of approvers for the department.

            This method is triggered whenever the 'department_id' field is modified.
            It searches for department approvers associated with the department and DM/CMs.
            The count of individual approvers is accumulated to determine the total number of approvers for the department.

        """
        for record in self:
            department_approvers = self.env['department.approvers'].search(
                [('dept_name', '=', record.department_id.id), ("approval_type.name", '=', 'DM CM')])
            count = 0
            for approver in department_approvers:
                count += approver.no_of_approvers
            record.approver_count = count

    # this check the status based on approval status and state.
    @api.depends('approval_status', 'state')
    def compute_check_status(self):
        """
        When installing approval_module_extension in this method compute_check_status comment out the for loop first.
        So it prevents automatically sending of email to already approved or disapproved PR/PO.
        After successfully installing the module. You can now uncomment the for loop and Upgrade the module.
        """
        for rec in self:
            if rec.approval_status == 'approved' or rec.state == 'approved':
                rec.get_approvers_email()
                rec.submit_to_final_approver()
            elif rec.approval_status == 'disapprove' or rec.state == 'disapprove':
                rec.get_approvers_email()
                rec.submit_for_disapproval()

    def update_check_status(self):
        self.check_status = False
        self.check_status = True

    def approval_dashboard_link(self):
        # Approval Dashboard Link Section
        approval_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        approval_action = self.env['ir.actions.act_window'].search(
            [('name', '=', 'Request')], limit=1)
        action_id = approval_action.id

        odoo_params = {
            "action": action_id,
        }

        query_string = '&'.join([f'{key}={value}' for key, value in odoo_params.items()])
        list_view_url = f"{approval_base_url}/web?debug=0#{query_string}"
        return list_view_url

    def edit_request_link(self):
        action = self.env['ir.actions.act_window'].search([('res_model', '=', 'tpc.dm.cm.request')], limit=1)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        result = re.sub(r'\((.*?)\)', '', str(action)).replace(',', '')
        res = f"{result},{action.id}"
        result = re.sub(r'\s*,\s*', ',', res)
        menu = self.env['ir.ui.menu'].search([('action', '=', result)], limit=1)
        params = {
            "id": self.id,
            "action": action.id,
            "model": "tpc.dm.cm.request",
            "view_type": "form",
            "cids": 1,
            "menu_id": menu.id
        }
        query_params = "&".join(f"{key}={value}" for key, value in params.items())
        pr_form_link = f"{base_url}/web#{query_params}"
        return pr_form_link

    def generate_odoo_link(self):
        # Generate Odoo Link Section
        action = self.env['ir.actions.act_window'].search([('res_model', '=', 'tpc.dm.cm.request')], limit=1)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        result = re.sub(r'\((.*?)\)', '', str(action)).replace(',', '')
        res = f"{result},{action.id}"
        result = re.sub(r'\s*,\s*', ',', res)

        menu = self.env['ir.ui.menu'].search([('action', '=', result)], limit=1)
        params = {
            "id": self.id,
            "action": action.id,
            "model": "tpc.dm.cm.request",
            "view_type": "form",
            "cids": 1,
            "menu_id": menu.id
        }
        query_params = "&".join(f"{key}={value}" for key, value in params.items())
        pr_form_link = f"{base_url}/web#{query_params}"
        return pr_form_link

    def generate_token(self):
        now = datetime.datetime.now()
        token = "{}-{}-{}-{}".format(self.id, self.name, self.env.user.id, now)
        return hashlib.sha256(token.encode()).hexdigest()

    # Initial Approver Sending of Email
    def submit_for_approval(self):
        # Approval Dashboard Link Section
        approval_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        approval_action = self.env['ir.actions.act_window'].search(
            [('name', '=', 'DM/CM Approval Dashboard')], limit=1)
        action_id = approval_action.id

        odoo_params = {
            "action": action_id,
        }

        query_string = '&'.join([f'{key}={value}' for key, value in odoo_params.items()])
        approval_list_view_url = f"{approval_base_url}/web?debug=0#{query_string}"

        # Generate Odoo Link Section
        odoo_action = self.env['ir.actions.act_window'].search([('res_model', '=', 'tpc.dm.cm.request')], limit=1)
        odoo_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        odoo_result = re.sub(r'\((.*?)\)', '', str(odoo_action)).replace(',', '')
        odoo_res = f"{odoo_result},{odoo_action.id}"
        odoo_result = re.sub(r'\s*,\s*', ',', odoo_res)

        odoo_menu = self.env['ir.ui.menu'].search([('action', '=', odoo_result)], limit=1)
        odoo_params = {
            "id": self.id,
            "action": odoo_action.id,
            "model": "tpc.dm.cm.request",
            "view_type": "form",
            "cids": 1,
            "menu_id": odoo_menu.id
        }
        odoo_query_params = "&".join(f"{key}={value}" for key, value in odoo_params.items())
        pr_form_link = f"{odoo_base_url}/web#{odoo_query_params}"

        self.generate_odoo_link()
        self.approval_dashboard_link()

        fetch_getEmailReceiver = self.approver_id.work_email  # self.approver_id.work_email DEFAULT RECEIVER CHANGE IT TO IF YOU WANT ----> IF YOU WANT TO SET AS DEFAULT OR ONLY ONE ##
        print(fetch_getEmailReceiver)
        self.sending_email(fetch_getEmailReceiver, pr_form_link, approval_list_view_url)

        self.write({
            'approval_status': 'pr_approval',
            'state': 'to_approve',
            'to_approve': True,
            'show_submit_request': False,
            'submit_for_approval_bool': False
        })

    def sending_email(self, fetch_getEmailReceiver, pr_form_link, approval_list_view_url):
        sender = 'noreply@teamglac.com'
        host = "192.168.1.114"
        port = 25
        username = "noreply@teamglac.com"
        password = "noreply"

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        token = self.generate_token()

        approval_url = "{}/tpc_dm_cm/request/approve/{}".format(base_url, token)
        disapproval_url = "{}/tpc_dm_cm/request/disapprove/{}".format(base_url, token)
        self.write({'approval_link': token})

        cc_emails = []
        bcc_emails = []

        person_emails = self.cc_bcc()

        for record in person_emails:

            if record.status == 'active':
                if record.cc:
                    print('CC is True, get CC email:', record.email)
                    cc_emails.append(record.email)  # Add CC email to the CC list
                    # Your logic to handle cc email when it's true

                if record.bcc:
                    print('BCC is True, get BCC email:', record.email)
                    bcc_emails.append(record.email)  # Add BCC email to the BCC list
                    # Your logic to handle bcc email when it's true

                # Your logic for further processing if needed

            elif record.status == 'inactive':
                # Handle inactive status if needed
                pass

            print('---')  # Separator for better readability

        print('CC Emails:', cc_emails)
        print('BCC Emails:', bcc_emails)

        cc_emails_str = ', '.join(cc_emails)
        bcc_emails_str = ', '.join(bcc_emails)

        msg = MIMEMultipart()
        msg['From'] = formataddr(('Odoo Mailer', sender))
        msg['To'] = fetch_getEmailReceiver
        msg['Cc'] = cc_emails_str
        msg['Bcc'] = bcc_emails_str
        msg['Subject'] = f'Billing Request Approval [{self.name}]'

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
                           <dt><b>Serial No. {self.name}</b></dt>
                               <br></br>
                                   <dd>Requested by: &nbsp;&nbsp;{self.user_id.name}</dd>
                                   <dd>Date Requested: &nbsp;&nbsp;{self.ordering_date}</dd>
                                   <dd>Department: &nbsp;&nbsp;{self._get_requesters_id()}</dd>
                                   <dd>Source: &nbsp;&nbsp;{self.source.source_trade_n_trade}</dd>
                                   <dd>Particulars: &nbsp;&nbsp;{self.particulars.particulars}</dd>
                               <br></br>
                                   <span><b>ITEMS REQUESTED</b></span>
                               <br></br>
                           """

        html_content += """
                        <br></br>
                        <table>
                                    <tr>
                                        <th>Product</th>
                                        <th>Label</th>
                                        <th>Cost</th>
                                        <th>Quantity</th>
                                        <th>Total</th>
                                        <th>Reference Docs</th>
                                    </tr>
                                    """

        for line in self.dm_cm_line:
            if isinstance(line.file_links, str):
                # Check if file_links is a string containing multiple URLs
                file_links_list = line.file_links.split('\n')
            elif isinstance(line.file_links, list):
                # Assume file_links is already a list of URLs
                file_links_list = line.file_links
            else:
                # If file_links is neither a string nor a list, handle accordingly
                file_links_list = []

            html_content += "<tr>"
            html_content += f"<td>{f'[{line.product.default_code}]{line.product.name}'}</td>"
            html_content += f"<td>{line.label}</td>"
            html_content += f"<td>{line.cost}</td>"
            html_content += f"<td>{line.quantity}</td>"
            html_content += f"<td>{line.total}</td>"

            # Generate HTML links based on the type of file_links
            if file_links_list:
                html_links = ", ".join([f'<a href="{link}">{link}</a>' for link in file_links_list])
                html_content += f'<td>{html_links}</td>'
            else:
                html_content += "<td></td>"  # If no file links, add an empty cell

            html_content += "</tr>"

        html_content += f"""
               </table>
               <br></br>
               </body>
               <br></br>
               <br></br>
               <br></br>
               <span style="font-style: italic;";><a href="{approval_url}" style="color: green;">ACKNOWLEDGE REQUEST</a> / <a href="{disapproval_url}"  style="color: red;">DISAPPROVE REQUEST</a>
               </html>
           """

        msg.attach(MIMEText(html_content, 'html'))

        try:
            smtpObj = smtplib.SMTP(host, port)
            smtpObj.login(username, password)
            recipients = [fetch_getEmailReceiver] + cc_emails + bcc_emails
            print(recipients)
            smtpObj.sendmail(sender, recipients, msg.as_string())
            print(fetch_getEmailReceiver, 'receiver')

            msg = "Successfully sent email"
            print(msg)
            return {
                'success': {
                    'title': 'Successfully email sent!',
                    'message': f'{msg}'}
            }
        except Exception as e:
            msg = f"Error: Unable to send email: {str(e)}"
            print(msg)
            return {
                'warning': {
                    'title': 'Error: Unable to send email!',
                    'message': f'{msg}'}
            }

    # Next Approver Sending of Email
    def submit_to_next_approver(self):
        # Approval Dashboard Link Section
        print('go to next step')

        approval_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        print(approval_base_url)
        approval_action = self.env['ir.actions.act_window'].search(
            [('name', '=', 'DM/CM Approval Dashboard')], limit=1)
        action_id = approval_action.id
        odoo_params = {
            "action": action_id,
        }

        query_string = '&'.join([f'{key}={value}' for key, value in odoo_params.items()])
        approval_list_view_url = f"{approval_base_url}/web?debug=0#{query_string}"
        print(approval_list_view_url)

        # Generate Odoo Link Section
        odoo_action = self.env['ir.actions.act_window'].search([('res_model', '=', 'tpc.dm.cm.request')], limit=1)
        odoo_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        odoo_result = re.sub(r'\((.*?)\)', '', str(odoo_action)).replace(',', '')
        odoo_res = f"{odoo_result},{odoo_action.id}"
        odoo_result = re.sub(r'\s*,\s*', ',', odoo_res)

        odoo_menu = self.env['ir.ui.menu'].search([('action', '=', odoo_result)], limit=1)
        odoo_params = {
            "id": self.id,
            "action": odoo_action.id,
            "model": "tpc.dm.cm.request",
            "view_type": "form",
            "cids": 1,
            "menu_id": odoo_menu.id
        }
        odoo_query_params = "&".join(f"{key}={value}" for key, value in odoo_params.items())
        pr_form_link = f"{odoo_base_url}/web#{odoo_query_params}"

        self.generate_odoo_link()
        self.approval_dashboard_link()

        fetch_getEmailReceiver = self.approver_id.work_email  # self.approver_id.work_email DEFAULT RECEIVER CHANGE IT TO IF YOU WANT ----> IF YOU WANT TO SET AS DEFAULT OR ONLY ONE ##
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

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        token = self.generate_token()

        approval_url = "{}/tpc_dm_cm/request/approve/{}".format(base_url, token)
        disapproval_url = "{}/tpc_dm_cm/request/disapprove/{}".format(base_url, token)

        self.write({'approval_link': token})
        print(token)
        print("main next", self.approval_link)

        msg = MIMEMultipart()
        msg['From'] = formataddr(('Odoo Mailer', sender))
        msg['To'] = fetch_getEmailReceiver
        msg['Subject'] = f'Billing Request Approval [{self.name}]'
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
                   <dt><b>Serial No. {self.name}</b></dt>
                       <br></br>
                           <dd>Requested by: &nbsp;&nbsp;{'' if not self.user_id else self.user_id.name}</dd>
                           <dd>Date Requested: &nbsp;&nbsp;{'' if not self.ordering_date else self.ordering_date}</dd>
                           <dd>Department: &nbsp;&nbsp;{self._get_requesters_id()}</dd>
                           <dd>Source: &nbsp;&nbsp;{'' if not self.source else self.source.source_trade_n_trade}</dd>
                           <dd>Particulars: &nbsp;&nbsp;{'' if not self.particulars else self.particulars.particulars}</dd>
                       <br></br>
                           <span><b>ITEMS REQUESTED</b></span>
                       <br></br>
                   """

        html_content += """
                        <br></br>
                        <table>
                                    <tr>
                                        <th>Product</th>
                                        <th>Label</th>
                                        <th>Cost</th>
                                        <th>Quantity</th>
                                        <th>Total</th>
                                        <th>Reference Docs</th>
                                    </tr>
                                    """

        for line in self.dm_cm_line:
            if isinstance(line.file_links, str):
                # Check if file_links is a string containing multiple URLs
                file_links_list = line.file_links.split('\n')
            elif isinstance(line.file_links, list):
                # Assume file_links is already a list of URLs
                file_links_list = line.file_links
            else:
                # If file_links is neither a string nor a list, handle accordingly
                file_links_list = []

            html_content += "<tr>"
            html_content += f"<td>{f'[{line.product.default_code}]{line.product.name}'}</td>"
            html_content += f"<td>{line.label}</td>"
            html_content += f"<td>{line.cost}</td>"
            html_content += f"<td>{line.quantity}</td>"
            html_content += f"<td>{line.total}</td>"

            # Generate HTML links based on the type of file_links
            if file_links_list:
                html_links = ", ".join([f'<a href="{link}">{link}</a>' for link in file_links_list])
                html_content += f'<td>{html_links}</td>'
            else:
                html_content += "<td></td>"  # If no file links, add an empty cell

            html_content += "</tr>"

        html_content += f"""
               </table>
               <br></br>
               </body>
               <br></br>
               <br></br>
               <br></br>
               <span style="font-style: italic;";><a href="{approval_url}" style="color: green;">ACKNOWLEDGE REQUEST</a> / <a href="{disapproval_url}"  style="color: red;">DISAPPROVE REQUEST</a>

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

    # PR is DISAPPROVED
    def submit_for_disapproval(self):
        # Generate Odoo Link Section
        odoo_action = self.env['ir.actions.act_window'].search([('res_model', '=', 'tpc.dm.cm.request')], limit=1)
        odoo_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        odoo_result = re.sub(r'\((.*?)\)', '', str(odoo_action)).replace(',', '')
        odoo_res = f"{odoo_result},{odoo_action.id}"
        odoo_result = re.sub(r'\s*,\s*', ',', odoo_res)

        odoo_menu = self.env['ir.ui.menu'].search([('action', '=', odoo_result)], limit=1)
        odoo_params = {
            "id": self.id,
            "action": odoo_action.id,
            "model": "tpc.dm.cm.request",
            "view_type": "form",
            "cids": 1,
            "menu_id": odoo_menu.id
        }
        odoo_query_params = "&".join(f"{key}={value}" for key, value in odoo_params.items())
        pr_form_link = f"{odoo_base_url}/web#{odoo_query_params}"

        self.generate_odoo_link()

        # fetch_getEmailReceiver = self.approver_id.work_email  # self.approver_id.work_email DEFAULT RECEIVER CHANGE IT TO IF YOU WANT ----> IF YOU WANT TO SET AS DEFAULT OR ONLY ONE ##
        # self.send_disapproval_email(fetch_getEmailReceiver, pr_form_link)
        email1 = self.initial_approver_email if self.initial_approver_email else ""
        email2 = self.second_approver_email if self.second_approver_email else ""
        email3 = self.third_approver_email if self.third_approver_email else ""
        email4 = self.fourth_approver_email if self.fourth_approver_email else ""
        email5 = self.final_approver_email if self.final_approver_email else ""
        email6 = self.purchase_rep_email if self.purchase_rep_email else ""

        self.send_disapproval_email([email1, email2, email3, email4, email5, email6], pr_form_link)

    def send_disapproval_email(self, recipient_list, pr_form_link):
        sender = 'noreply@teamglac.com'
        host = "192.168.1.114"
        port = 25
        username = "noreply@teamglac.com"
        password = "noreply"

        token = self.generate_token()
        self.write({'approval_link': token})

        msg = MIMEMultipart()
        msg['From'] = formataddr(('Odoo Mailer', sender))

        msg['To'] = ', '.join(recipient_list)
        msg['Subject'] = f'Billing Request Disapproved [{self.name}]'

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
                <dt><b>Serial No. {self.name}</b></dt>
                    <br></br>
                        <dd style='display: none;'>{self.get_current_date()}</d>
                        <dd>Requested by: &nbsp;&nbsp;{self.user_id.name if self.user_id.name != False else ""}</dd>
                        <dd>Date Requested: &nbsp;&nbsp;{self.ordering_date if self.ordering_date != False else ""}</dd>
                        <dd>Disapproved by: &nbsp;&nbsp;{self.env.user.name if self.env.user.name != False else ""}</dd>
                        <dd>Disapproval date: &nbsp;&nbsp;{self.date_today if self.date_today != False else ""}</dd>
                        <dd>Reason for Disapproval: &nbsp;&nbsp;{self.disapproval_reason if self.disapproval_reason != False else ""}</dd>
                    <br></br>
                    <br></br>
                    <br></br>
                        <span><b>ITEMS REQUESTED</b></span>
                    <br></br>
                """

        html_content += """
                <br></br>
                <table>
                            <tr>
                                <th>Product</th>
                                <th>Label</th>
                                <th>Cost</th>
                                <th>Quantity</th>
                                <th>Total</th>
                                <th>Reference Docs</th>
                            </tr>
                            """

        for line in self.dm_cm_line:
            if isinstance(line.file_links, str):
                # Check if file_links is a string containing multiple URLs
                file_links_list = line.file_links.split('\n')
            elif isinstance(line.file_links, list):
                # Assume file_links is already a list of URLs
                file_links_list = line.file_links
            else:
                # If file_links is neither a string nor a list, handle accordingly
                file_links_list = []

            html_content += "<tr>"
            html_content += f"<td>{f'[{line.product.default_code}]{line.product.name}'}</td>"
            html_content += f"<td>{line.label}</td>"
            html_content += f"<td>{line.cost}</td>"
            html_content += f"<td>{line.quantity}</td>"
            html_content += f"<td>{line.total}</td>"

            # Generate HTML links based on the type of file_links
            if file_links_list:
                html_links = ", ".join([f'<a href="{link}">{link}</a>' for link in file_links_list])
                html_content += f'<td>{html_links}</td>'
            else:
                html_content += "<td></td>"  # If no file links, add an empty cell

            html_content += "</tr>"

        html_content += f"""
                    </table>
                    <br></br>
                    </body>
                    <br></br>
                    <br></br>
                    <br></br>
                    <span> <a href="{pr_form_link}" style="color: blue;">ODOO PR FORM</span>

                    </html>
                """
        msg.attach(MIMEText(html_content, 'html'))

        try:
            smtpObj = smtplib.SMTP(host, port)
            smtpObj.login(username, password)
            smtpObj.sendmail(sender, recipient_list, msg.as_string())

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

    # PR is approved by final approver
    def submit_to_final_approver(self):
        # Use a list for emails
        emails = [
            self.initial_approver_email,
            self.second_approver_email,
            self.third_approver_email,
            self.fourth_approver_email,
            self.final_approver_email,
            self.purchase_rep_email,
        ]

        # Simplify email retrieval using a loop
        email_list = [email if email else "" for email in emails]

        # Check if the flag is True
        if self.flag:
            # Create empty lists to store email addresses


            # Check for email addresses based on the source condition
            if self.source.source_trade_n_trade == 'Trade':
                email_list_ar = []
                for rec in self.source.source_ar_lines:
                    if rec.email:
                        email_list_ar.append(rec.email)
                        print('iam going in trade')

            elif self.source.source_trade_n_trade == 'Non-Trade':
                email_list_sales = []
                email_list_ar = []
                for rec in self.source.source_ar_lines:
                    if rec.email:
                        email_list_ar.append(rec.email)
                for rec in self.source.source_sales_lines:
                    if rec.email:
                        email_list_sales.append(rec.email)

            else:
                # Call the send_to_final_approver_email function with the appropriate email list
                self.send_to_final_approver_email(email_list)

        # Add a return statement indicating the completion of the function
        # return "Submission to final approver complete."

        # else:
            #     mails = self.get_all_email_attached()
            #     self.notify_all_after_approved(mails)
        # else:
        #     mails = self.get_all_email_attached()
        #     self.notify_all_after_approved(mails)

    def status_trade(self):
        print('trigger')
        self.write({
            'approval_status': 'pr_approval',
            'state': 'to_approve',
            'to_approve': True,
            'show_submit_request': False
        })

    def check_final_approver(self):
        if self.trade_final_approver is not None:
            print(self.trade_final_approver.login, 'testtttt')
        else:
            raise ValueError("A string literal cannot contain NUL (0x00) characters.")

    def _final_approver(self):
        if self.trade_final_approver is not None:
            return self.trade_final_approver.login
        else:
            raise ValueError("A string literal cannot contain NUL (0x00) characters.")

    def _last_approver_function(self):
        try:
            date_now = datetime.datetime.now()
            formatted_date = date_now.strftime("%Y-%m-%d")

            self.write({
                'approval_status': 'approved',
                'state': 'approved',
                'to_approve': False,
                '_trade_final_approver': True,
                'show_submit_request': False,
                '_trade_final_approver_date_approver': formatted_date
            })

        except Exception as e:
            print(f"Error during write operation: {e}")

    def test_function(self):
        try:
            date_now = datetime.datetime.now()
            formatted_date = date_now.strftime("%Y-%m-%d")

            # self.write({
            #     # 'approval_status': 'approved',
            #     'state': 'approved',
            #     # 'to_approve': False,
            #     # '_trade_final_approver': True,
            #     # 'show_submit_request': False,
            #     # '_trade_final_approver_date_approver': formatted_date
            # })
            self.write({'state': 'approved'})

        except Exception as e:
            print(f"Error during write operation: {e}")

    def notify_all_after_approved(self, recipient_list):
        sender = 'noreply@teamglac.com'
        host = "192.168.1.114"
        port = 25
        username = "noreply@teamglac.com"
        password = "noreply"

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        token = self.generate_token()
        self.write({'approval_link': token})

        dashboard = "{}/tpc_dm_cm/request/dashboard/{}".format(base_url, token)

        cc_emails = []
        bcc_emails = []

        person_emails = self.cc_bcc()

        for record in person_emails:

            if record.status == 'active':
                if record.cc:
                    print('CC is True, get CC email:', record.email)
                    cc_emails.append(record.email)  # Add CC email to the CC list
                    # Your logic to handle cc email when it's true

                if record.bcc:
                    print('BCC is True, get BCC email:', record.email)
                    bcc_emails.append(record.email)  # Add BCC email to the BCC list
                    # Your logic to handle bcc email when it's true

                # Your logic for further processing if needed

            elif record.status == 'inactive':
                # Handle inactive status if needed
                pass

            print('---')  # Separator for better readability

        print('CC Emails:', cc_emails)
        print('BCC Emails:', bcc_emails)

        cc_emails_str = ', '.join(cc_emails)
        bcc_emails_str = ', '.join(bcc_emails)

        msg = MIMEMultipart()
        msg['From'] = formataddr(('Odoo Mailer', sender))

        msg['To'] = ', '.join(recipient_list)
        msg['Cc'] = cc_emails_str
        msg['Bcc'] = bcc_emails_str
        msg['Subject'] = f'Billing Request Approved: Please Review [{self.name}] and Confirm'

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
                   <dt><b>Serial No. {self.name}</b></dt>
                       <br></br>
                           <dd>Requested by: &nbsp;&nbsp;{'' if not self.user_id else self.user_id.name}</dd>
                           <dd>Date Requested: &nbsp;&nbsp;{'' if not self.ordering_date else self.ordering_date}</dd>
                           <dd>Department: &nbsp;&nbsp;{self._get_requesters_id()}</dd>
                           <dd>Source: &nbsp;&nbsp;{'' if not self.source else self.source.source_trade_n_trade}</dd>
                           <dd>Particulars: &nbsp;&nbsp;{'' if not self.particulars else self.particulars.particulars}</dd>
                       <br></br>
                           <span><b>ITEMS REQUESTED</b></span>
                       <br></br>
                   """

        html_content += """
                   <br></br>
                   <table>
                               <tr>
                                   <th>Product</th>
                                   <th>Label</th>
                                   <th>Cost</th>
                                   <th>Quantity</th>
                                   <th>Total</th>
                                   <th>Reference Documents</th>
                               </tr>
                               """

        for line in self.dm_cm_line:
            if isinstance(line.file_links, str):
                # Check if file_links is a string containing multiple URLs
                file_links_list = line.file_links.split('\n')
            elif isinstance(line.file_links, list):
                # Assume file_links is already a list of URLs
                file_links_list = line.file_links
            else:
                # If file_links is neither a string nor a list, handle accordingly
                file_links_list = []

            html_content += "<tr>"
            html_content += f"<td>{f'[{line.product.default_code}]{line.product.name}'}</td>"
            html_content += f"<td>{line.label}</td>"
            html_content += f"<td>{line.cost}</td>"
            html_content += f"<td>{line.quantity}</td>"
            html_content += f"<td>{line.total}</td>"

            # Generate HTML links based on the type of file_links
            if file_links_list:
                html_links = ", ".join([f'<a href="{link}">{link}</a>' for link in file_links_list])
                html_content += f'<td>{html_links}</td>'
            else:
                html_content += "<td></td>"  # If no file links, add an empty cell

            html_content += "</tr>"

        html_content += f"""
                       </table>
                       <br><br>
                       </body>
                       <br><br>
                       <br><br>
                       <br><br>
                       <span style="font-style: italic;">REQUESTS CAN BE ACCESSED VIA THIS LINK <a href="{dashboard}" style="color: green; font-weight:bold">CLICK HERE</a></span>
                       </html>
                       """

        msg.attach(MIMEText(html_content, 'html'))

        try:
            smtpObj = smtplib.SMTP(host, port)
            smtpObj.login(username, password)
            smtpObj.sendmail(sender, recipient_list, msg.as_string())

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

    def submit_to_last_approver(self):
        sender = 'noreply@teamglac.com'
        host = "192.168.1.114"
        port = 25
        username = "noreply@teamglac.com"
        password = "noreply"

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        token = self.generate_token()
        self.write({
            'approval_link': token,
            'submit_for_approve_bool': False
        })

        approval_url = "{}/tpc_dm_cm/request/final_approve/{}".format(base_url, token)
        disapproval_url = "{}/tpc_dm_cm/request/disapprove/{}".format(base_url, token)

        msg = MIMEMultipart()
        msg['From'] = formataddr(('Odoo Mailer', sender))

        msg['To'] = self._final_approver()
        msg['Subject'] = f'Billing Request for Costing [{self.name}]'

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
                   <dt><b>Serial No. {self.name}</b></dt>
                       <br></br>
                           <dd>Requested by: &nbsp;&nbsp;{'' if not self.user_id else self.user_id.name}</dd>
                           <dd>Date Requested: &nbsp;&nbsp;{'' if not self.ordering_date else self.ordering_date}</dd>
                           <dd>Department: &nbsp;&nbsp;{self._get_requesters_id()}</dd>
                           <dd>Source: &nbsp;&nbsp;{'' if not self.source else self.source.source_trade_n_trade}</dd>
                           <dd>Particulars: &nbsp;&nbsp;{'' if not self.particulars else self.particulars.particulars}</dd>
                       <br></br>
                           <span><b>ITEMS REQUESTED</b></span>
                       <br></br>
                   """

        html_content += """
                   <br></br>
                   <table>
                               <tr>
                                   <th>Product</th>
                                   <th>Label</th>
                                   <th>Cost</th>
                                   <th>Quantity</th>
                                   <th>Total</th>
                                   <th>Reference Documents</th>
                               </tr>
                               """

        for line in self.dm_cm_line:
            if isinstance(line.file_links, str):
                # Check if file_links is a string containing multiple URLs
                file_links_list = line.file_links.split('\n')
            elif isinstance(line.file_links, list):
                # Assume file_links is already a list of URLs
                file_links_list = line.file_links
            else:
                # If file_links is neither a string nor a list, handle accordingly
                file_links_list = []

            html_content += "<tr>"
            html_content += f"<td>{f'[{line.product.default_code}]{line.product.name}'}</td>"
            html_content += f"<td>{line.label}</td>"
            html_content += f"<td>{line.cost}</td>"
            html_content += f"<td>{line.quantity}</td>"
            html_content += f"<td>{line.total}</td>"

            # Generate HTML links based on the type of file_links
            if file_links_list:
                html_links = ", ".join([f'<a href="{link}">{link}</a>' for link in file_links_list])
                html_content += f'<td>{html_links}</td>'
            else:
                html_content += "<td></td>"  # If no file links, add an empty cell

            html_content += "</tr>"

        html_content += f"""
                       </table>
                       <br></br>
                       </body>
                       <br></br>
                       <br></br>
                       <br></br>
                       <span style="font-style: italic;";><a href="{approval_url}" style="color: green;">APPROVED REQUEST</a><a href="{disapproval_url}" style="color: red;">DISAPPROVED REQUEST</a>

                       </html>
                   """

        msg.attach(MIMEText(html_content, 'html'))

        try:
            smtpObj = smtplib.SMTP(host, port)
            smtpObj.login(username, password)
            smtpObj.sendmail(sender, self._final_approver(), msg.as_string())

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

    def notif_final_approver(self, TradeNTrade):
        sender = 'noreply@teamglac.com'
        host = "192.168.1.114"
        port = 25
        username = "noreply@teamglac.com"
        password = "noreply"

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        token = self.generate_token()
        self.write({'approval_link': token})

        approval_url = "{}/tpc_dm_cm/request/edit_request/{}".format(base_url, token)
        disapproval_url = "{}/tpc_dm_cm/request/disapprove/{}".format(base_url, token)

        msg = MIMEMultipart()
        msg['From'] = formataddr(('Odoo Mailer', sender))

        email_list = []  # Create an empty list to store email addresses

        if self.source.source_trade_n_trade == 'Trade':
            for rec in self.source.source_ar_lines:
                email_list.append(rec.email)  # Add each email to the list


        elif self.source.source_trade_n_trade == 'Non-Trade':
            pass

        else:
            print('Error')

        msg['To'] = ', '.join(email_list)
        msg['Subject'] = f'Billing Request for {TradeNTrade} [{self.name}]'

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
                   <dt><b>Serial No. {self.name}</b></dt>
                       <br></br>
                           <dd>Requested by: &nbsp;&nbsp;{'' if not self.user_id else self.user_id.name}</dd>
                           <dd>Date Requested: &nbsp;&nbsp;{'' if not self.ordering_date else self.ordering_date}</dd>
                           <dd>Department: &nbsp;&nbsp;{self._get_requesters_id()}</dd>
                           <dd>Source: &nbsp;&nbsp;{'' if not self.source else self.source.source_trade_n_trade}</dd>
                           <dd>Particulars: &nbsp;&nbsp;{'' if not self.particulars else self.particulars.particulars}</dd>
                       <br></br>
                           <span><b>ITEMS REQUESTED</b></span>
                       <br></br>
                   """

        html_content += """
                   <br></br>
                   <table>
                               <tr>
                                   <th>Product</th>
                                   <th>Label</th>
                                   <th>Cost</th>
                                   <th>Quantity</th>
                                   <th>Total</th>
                                   <th>Reference Documents</th>
                               </tr>
                               """

        for line in self.dm_cm_line:
            if isinstance(line.file_links, str):
                # Check if file_links is a string containing multiple URLs
                file_links_list = line.file_links.split('\n')
            elif isinstance(line.file_links, list):
                # Assume file_links is already a list of URLs
                file_links_list = line.file_links
            else:
                # If file_links is neither a string nor a list, handle accordingly
                file_links_list = []

            html_content += "<tr>"
            html_content += f"<td>{f'[{line.product.default_code}]{line.product.name}'}</td>"
            html_content += f"<td>{line.label}</td>"
            html_content += f"<td>{line.cost}</td>"
            html_content += f"<td>{line.quantity}</td>"
            html_content += f"<td>{line.total}</td>"

            # Generate HTML links based on the type of file_links
            if file_links_list:
                html_links = ", ".join([f'<a href="{link}">{link}</a>' for link in file_links_list])
                html_content += f'<td>{html_links}</td>'
            else:
                html_content += "<td></td>"  # If no file links, add an empty cell

            html_content += "</tr>"

        html_content += f"""
                       </table>
                       <br></br>
                       </body>
                       <br></br>
                       <br></br>
                       <br></br>
                       <span style="font-style: italic;";><a href="{approval_url}" style="color: green;">EDIT REQUEST</a>

                       </html>
                   """

        msg.attach(MIMEText(html_content, 'html'))

        try:
            smtpObj = smtplib.SMTP(host, port)
            smtpObj.login(username, password)
            smtpObj.sendmail(sender, email_list, msg.as_string())

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

    def send_to_final_approver_email(self, recipient_list):
        sender = 'noreply@teamglac.com'
        host = "192.168.1.114"
        port = 25
        username = "noreply@teamglac.com"
        password = "noreply"

        token = self.generate_token()
        self.write({'approval_link': token})

        msg = MIMEMultipart()
        msg['From'] = formataddr(('Odoo Mailer', sender))

        msg['To'] = ', '.join(recipient_list)
        msg['Subject'] = 'DM/CM Approved [' + self.name + ']'

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
                  <dt><b>Serial No. {self.name}</b></dt>
                   <dd style='display: none;'>{self.approver_count}</dd>
                      <br></br>
                          <dd>Requested by: &nbsp;&nbsp;{self.user_id.name if self.user_id.name != False else ""}</dd>
                          <dd>Date Requested: &nbsp;&nbsp;{self.ordering_date if self.ordering_date != False else ""}</dd>
                  """

        if self.approver_count >= 1:
            if self.approver_count == 1:
                html_content += f"""
                                      <dd>{'Final ' if self.approver_count == 1 else 'Initial'} Approval By: {self.final_approver_name}</dd>
                                      <dd>{'Final ' if self.approver_count == 1 else 'Initial'} Approval Date: {self.final_approval_date if self.final_approval_date != False else ""}</dd>
                                      """
            elif self.approver_count > 1:
                html_content += f"""
                       <dd>Initial Approval By: {self.initial_approver_name}</dd>
                       <dd>Initial Approval Date:  &nbsp;&nbsp;{self.initial_approval_date if self.initial_approval_date != False else ""}</dd>
               """

        if self.approver_count >= 2:
            if self.approver_count == 2:
                html_content += f"""
                       <dd>{'Final ' if self.approver_count == 2 else 'Second'} Approval By: {self.final_approver_name}</dd>
                       <dd>{'Final ' if self.approver_count == 2 else 'Second'} Approval Date: {self.final_approval_date if self.final_approval_date != False else ""}</dd>
                       """
            elif self.approver_count > 2:
                html_content += f"""
                       <dd>Second Approval By: {self.second_approver_name}</dd>
                       <dd>Second Approval Date: {self.second_approval_date if self.second_approval_date != False else ""}</dd>
                   """
            else:
                return False

        if self.approver_count >= 3:
            if self.approver_count == 3:
                html_content += f"""
                      <dd>{'Final ' if self.approver_count == 3 else 'Third'} Approval By: {self.final_approver_name}</dd>
                      <dd>{'Final ' if self.approver_count == 3 else 'Third'} Approval Date: {self.final_approval_date if self.final_approval_date != False else ""}</dd>
                      """
            elif self.approver_count > 3:
                html_content += f"""
                      <dd>Third Approval By: {self.third_approver_name}</dd>
                      <dd>Third Approval Date: {self.third_approval_date if self.third_approval_date != False else ""}</dd>
                  """
            else:
                return False

        if self.approver_count >= 4:
            if self.approver_count == 4:
                html_content += f"""
                        <dd>{'Final ' if self.approver_count == 4 else 'Fourth'} Approval By: {self.final_approver_name}</dd>
                        <dd>{'Final ' if self.approver_count == 4 else 'Fourth'} Approval Date: {self.final_approval_date if self.final_approval_date != False else ""}</dd>
                        """
            elif self.approver_count > 4:
                html_content += f"""
                        <dd>Fourth Approval By: {self.fourth_approver_name}</dd>
                        <dd>Fourth Approval Date: {self.fourth_approval_date if self.fourth_approval_date != False else ""}</dd>
                    """
            else:
                return False

        if self.approver_count >= 5:
            html_content += f"""
                    <dd>Final Approval By: {self.final_approver_name}</dd>
                    <dd>Final Approval Date: {self.final_approval_date if self.final_approval_date != False else ""}</dd>
                """

        html_content += f"""
                <br></br>
                <br></br>
                <br></br>
                <span><b>ITEMS REQUESTED</b></span>
                <br></br>
                """

        html_content += """
                        <br></br>
                        <table>
                                    <tr>
                                        <th>Product</th>
                                        <th>Label</th>
                                        <th>Cost</th>
                                        <th>Quantity</th>
                                        <th>Total</th>
                                        <th>Reference Docs</th>
                                    </tr>
                                    """

        for line in self.dm_cm_line:
            if isinstance(line.file_links, str):
                # Check if file_links is a string containing multiple URLs
                file_links_list = line.file_links.split('\n')
            elif isinstance(line.file_links, list):
                # Assume file_links is already a list of URLs
                file_links_list = line.file_links
            else:
                # If file_links is neither a string nor a list, handle accordingly
                file_links_list = []

            html_content += "<tr>"
            html_content += f"<td>{f'[{line.product.default_code}]{line.product.name}'}</td>"
            html_content += f"<td>{line.label}</td>"
            html_content += f"<td>{line.cost}</td>"
            html_content += f"<td>{line.quantity}</td>"
            html_content += f"<td>{line.total}</td>"

            # Generate HTML links based on the type of file_links
            if file_links_list:
                html_links = ", ".join([f'<a href="{link}">{link}</a>' for link in file_links_list])
                html_content += f'<td>{html_links}</td>'
            else:
                html_content += "<td></td>"  # If no file links, add an empty cell

            html_content += "</tr>"

        html_content += f"""
                    </table>
                    <br></br>
                  
                    </body>
                    <br></br>
                    </html>
                """

        msg.attach(MIMEText(html_content, 'html'))

        try:
            smtpObj = smtplib.SMTP(host, port)
            smtpObj.login(username, password)
            smtpObj.sendmail(sender, recipient_list, msg.as_string())

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

    def compute_approver(self):
        for rec in self:
            if self.env.user.name == rec.approver_id.name:
                self.update({
                    'is_approver': True,
                })
            else:
                self.update({
                    'is_approver': False,
                })

    @api.onchange('department_id', 'approval_stage')
    def get_approver_domain(self):
        for rec in self:
            domain = []
            res = self.env["department.approvers"].search(
                [("dept_name", "=", rec.department_id.id), ("approval_type.name", '=', 'DM CM')])

            if rec.department_id and rec.approval_stage == 1:
                try:
                    approver_dept = [x.first_approver.id for x in res.set_first_approvers]
                    rec.approver_id = approver_dept[0]
                    domain.append(('id', '=', approver_dept))

                except IndexError:
                    raise UserError(_("No Approvers set for {}!").format(rec.department_id.name))

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

    @api.depends('approval_stage')
    def pr_approve_request(self):
        for rec in self:
            res = self.env["department.approvers"].search(
                [("dept_name", "=", rec.department_id.id), ("approval_type.name", '=', 'DM CM')])

            if rec.approver_id and rec.approval_stage < res.no_of_approvers:
                if rec.approval_stage == 1:

                    if self.initial_approver_name is None:
                        raise UserError('No approver set')
                    else:
                        self.initial_approver_name = rec.approver_id.name

                    approver_dept = [x.second_approver.id for x in res.set_second_approvers]

                    self.write({
                        'approver_id': approver_dept[0]
                    })

                    self.submit_to_next_approver()
                    self.get_current_date()

                if rec.approval_stage == 2:
                    if self.second_approver_name is None:
                        raise UserError('No approver set')
                    else:
                        self.second_approver_name = rec.approver_id.name
                    approver_dept = [x.third_approver.id for x in res.set_third_approvers]

                    self.write({
                        'approver_id': approver_dept[0]
                    })

                    self.submit_to_next_approver()
                    self.get_current_date()

                if rec.approval_stage == 3:
                    if self.third_approver_name is None:
                        raise UserError('No approver set')
                    else:
                        self.third_approver_name = rec.approver_id.name

                    approver_dept = [x.fourth_approver.id for x in res.set_fourth_approvers]

                    self.write({
                        'approver_id': approver_dept[0]
                    })

                    self.submit_to_next_approver()
                    self.get_current_date()

                if rec.approval_stage == 4:
                    if self.fourth_approver_name is None:
                        raise UserError('No approver set')
                    else:
                        self.fourth_approver_name = rec.approver_id.name

                    approver_dept = [x.fifth_approver.id for x in res.set_fifth_approvers]

                    self.write({
                        'approver_id': approver_dept[0]
                    })

                    self.submit_to_next_approver()
                    self.get_current_date()

                rec.approval_stage += 1
            else:
                self.write({
                    'state': 'approved',
                    'approval_status': 'approved',
                    'final_approver_name': rec.approver_id.name,
                })
                self.get_current_date()

    def button_cancel(self):
        for order in self:
            for inv in order.invoice_ids:
                if inv and inv.state not in ('cancel', 'draft'):
                    raise UserError(
                        _("Unable to cancel this purchase order. You must first cancel the related vendor bills."))

        self.write({'state': 'cancel',
                    'approval_status': 'cancel'})

    def generate_credit_memo(self):
        data = {
            'tpc_dm_cm_connection': self.id,
            'ref': self.name
        }
        try:
            self.write({
                'credit_memo_request_final_submit': False
            })
            self._credit_memo(data)
        except Exception as e:
            print(f"Error creating record: {e}")

    def generate_debit_memo(self):
        data = {
            'tpc_dm_cm_connection': self.id,
            'ref': self.name
        }
        try:
            self.write({
                'debit_memo_request_final_submit': False
            })
            self._debit_memo(data)
        except Exception as e:
            print(f"Error creating record: {e}")

    def _debit_memo(self, data):
        try:
            new_record = self.env['account.move'].create({
                'name': '/',
                'ref': data['ref'],
                'type': 'out_invoice',
                'is_debit_note': True,
                'tpc_dm_cm_connection': data['tpc_dm_cm_connection']
                # Add other fields accordingly
            })
            self._create_debit_memo_connection(new_record)
            return new_record.id
        except Exception as e:
            raise ValueError("Error. {}".format(e))

    def _credit_memo(self, data):
        print(data['ref'], 'credit')
        try:
            new_record = self.env['account.move'].create({
                'name': '/',
                'ref': data['ref'],
                'type': 'out_refund',
                'is_debit_note': False,
                'tpc_dm_cm_connection': data['tpc_dm_cm_connection']
                # Add other fields accordingly
            })
            self._create_credit_memo_connection(new_record)
            return new_record.id
        except Exception as e:
            raise ValueError("Error. {}".format(e))

    def _create_debit_memo_connection(self, id):
        create = self.debit_note = id
        return create

    def _create_credit_memo_connection(self, id):
        create = self.credit_note = id
        return create

    def _get_requesters_id(self):
        other_model_records = self.env['hr.employee'].search([('user_id', '=', self.user_id.id)])
        if other_model_records.department_id is None or other_model_records.department_id is False:
            return ''
        else:
            return other_model_records.department_id.name


class TpcDmCmRequestLine(models.Model):
    _name = 'tpc.dm.cm.request.line'
    _description = 'Team Pacific Corporation DM CM'

    dm_cm = fields.Many2one('tpc.dm.cm.request', string='DM/CM')
    product = fields.Many2one('product.product', string='Product')
    label = fields.Char(string='Label')
    cost = fields.Selection([
        ('for_costing', 'For Costing'),
        ('input_cost', 'Input Cost')
    ], string='Input Cost or For Costing', required=True)
    input_cost_field = fields.Float(string='Cost')
    quantity = fields.Float(string='Quantity')
    total = fields.Float(string='Total')
    reference_doc = fields.Many2many("ir.attachment", string='Reference Doc.', required=True)
    file_links = fields.Text(string='File Links', compute='_compute_file_links', store=True)

    # Helper method to set attachments as public

    @api.onchange('quantity')
    def compute_cost(self):
        for cost in self:
            if cost.cost == 'input_cost':
                if cost.input_cost_field is not None and cost.input_cost_field is not False:
                    self.total = cost.input_cost_field * cost.quantity

    @api.depends('reference_doc')
    def _compute_file_links(self):
        for record in self:
            links = []
            for attachment in record.reference_doc:
                links.append(self.get_file_link(attachment))
            record.file_links = '\n'.join(links)

    def get_module_static_path(self):
        module_path = os.path.dirname(os.path.realpath(__file__))
        static_path = os.path.join(module_path, '../static', 'uploads')

        if not os.path.exists(static_path):
            os.makedirs(static_path)

        return static_path

    def create(self, vals):
        record = super(TpcDmCmRequestLine, self).create(vals)
        self.save_files_to_static_folder(record)
        if record.reference_doc:
            attachments = self.env['ir.attachment'].browse(record.reference_doc.ids)
            attachments.write({'public': True})
        return record

    def write(self, vals):
        result = super(TpcDmCmRequestLine, self).write(vals)
        self.save_files_to_static_folder(result)
        if result.reference_doc:
            attachments = self.env['ir.attachment'].browse(result.reference_doc.ids)
            attachments.write({'public': True})
        return result

    def save_files_to_static_folder(self, record):
        static_folder_path = self.get_module_static_path()

        for attachment in record.reference_doc:
            file_data = attachment.datas
            if file_data:
                file_name = self.generate_unique_filename(attachment.name)
                file_path = os.path.join(static_folder_path, file_name)
                with open(file_path, 'wb') as file:
                    file.write(base64.b64decode(file_data))

                # Update the attachment record with the correct store_fname
                attachment.write({'store_fname': file_name})

    def generate_unique_filename(self, original_filename):
        unique_id = hashlib.sha256(os.urandom(8)).hexdigest()[:8]
        filename, extension = os.path.splitext(original_filename)
        return f"{filename}_{unique_id}{extension}"

    def get_file_link(self, attachment):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        print(f"{base_url}/web/content/{attachment.id}/{attachment.name}")
        return f"{base_url}/web/content/{attachment.id}/{attachment.name}"


class TpcDmCmRequestEmail(models.Model):
    _name = 'tpc.dm.cm.request.email'
    _description = 'Team Pacific Corporation DM CM'

    dm_cm_email = fields.Many2one('tpc.dm.cm.request')
    name = fields.Many2one('email.control', string='Employee')
    email = fields.Char(related='name.email', string='Employee')
    group = fields.Many2one(related='name.group', string='Group', store=True)
    status = fields.Selection(related='name.status', string='Status', store=True)
    cc = fields.Boolean(related='name.cc', string='CC', store=True)
    bcc = fields.Boolean(related='name.bcc', string='BCC', store=True)
