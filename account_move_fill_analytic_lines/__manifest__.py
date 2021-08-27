# -*- coding: utf-8 -*-
{
    'name': 'Botón cuentas analíticas para líneas de facturas de proveedor',
    'version': '1.0',
    'category': 'Accounting',
    'sequence': 1,
    'description': """
        Se agrega un campo de cuenta analítica y un botón para poder llenar todas las cuentas analíticas de las líneas de la factura
    """,
    'author': 'Grupo OLA',
    'depends': ['account'],
    'data': ['views/account_move_views.xml',
             ],
    'installable': True,
    'auto_install': False,
}
