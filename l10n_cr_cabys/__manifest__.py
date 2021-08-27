{
    "name": "L10N CR CAByS",
    "version": "14.0.0.1.0",
    "author": "HomebrewSoft",
    "website": "https://homebrewsoft.dev",
    "license": "LGPL-3",
    "depends": [
        # TODO depends and create XML
        "account",
        "product",
        "l10n_cr_accounting",
    ],
    "data": [
        # security
        "security/ir.model.access.csv",
        # data
        "data/functions.xml",
        "data/function_update_tax_ids.xml",
        "data/ir_cron.xml",
        # reports
        # views
        "views/cabys.xml",
        "views/product_template.xml",
    ],
}
