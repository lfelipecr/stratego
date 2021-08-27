{
    "name": "L10N CR Import",
    "version": "14.0.0.3",
    "author": "HomebrewSoft",
    "website": "https://homebrewsoft.dev",
    "license": "LGPL-3",
    "depends": [
        "account",
        "sale",
        "l10n_cr_accounting",
    ],
    "data": [
        # security
        "security/ir.model.access.csv",
        # data
        "data/reference_document_data.xml",
        # wizards
        "wizard/account_invoice_import_view.xml",
        "wizard/account_invoice_import_view2.xml",
        # views
        "views/account_config_settings.xml",
        "views/account_invoice_import_config.xml",
        "views/account_move.xml",
        "views/account_journal.xml",
        "views/reference_document_views.xml",
        "views/res_partner.xml",
    ],
}
