# -*- coding: utf-8 -*-
{
    'name': "approval_module_extension",
    'sequence': 0,

    'summary': """
       Approval Module Extension For Odoo 13""",

    'description': """
        Approval Module Extension 
    """,

    'author': "Alex Fernan Mercado",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
     'depends': ['account', 'purchase', 'stock', 'purchase_stock', 'om_account_accountant', 'om_account_asset', 'om_account_budget',
                'team_accounting', 'accounting_pdf_reports', 'mrp', 'sale', 'purchase_requisition', 'approval_module'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/purchase_requisition_view.xml',
        'views/purchase_order_view.xml',

    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
