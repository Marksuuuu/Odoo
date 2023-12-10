# pylint: disable=manifest-required-author
{

    'name': "Debit Notes",

    'summary': """
        Debit Notes
        ===========
        |The specific and easy-to-use Debit system in Odoo allows you to keep track of your accounting, even when you are not an accountant. It provides an easy way to follow up on your vendors and customers.
        
        |You could use this simplified accounting in case you work with an (external) account to keep your books, and you still want to keep track of payments. This module also offers you an easy method of registering payments, without having to encode complete abstracts of account.
            """,

    'author': "Agile Software Solutions and Technologies OPC",
    'website': "https://agiletech.ph",


    # any module necessary for this one to work correctly
    'depends': ['account', 'purchase', 'om_account_accountant', 'om_account_asset', 'om_account_budget', 'team_accounting', 'accounting_pdf_reports'],

    # always loaded
    'data': [
        'data/account_data.xml',
        'views/account_move_views.xml',
        'views/account_view.xml',
        'views/bills_to_transfer_views.xml',
        'views/account_asset_views.xml',
    ],
    'license': 'LGPL-3',
}
