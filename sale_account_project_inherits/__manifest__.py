# -*- coding: utf-8 -*-
{
    'name': 'Sale account project inherits',
    'version': '1.0',
    'category': 'Sale',
    'sequence': 1,
    'description': """
        
    """,
    'author': 'Grupo OLA',
    'depends': ['sale', 'product'],
    'data': ['views/sale_views.xml',
             'views/product_views.xml',
             'report/sale_report.xml',
             'report/sale_report_templates.xml',
             'security/ir.model.access.csv',
             ],
    'installable': True,
    'auto_install': False,
}
