from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    students = env['student.student'].search([('partner_id', '=', False)])
    for student in students:
        partner = env['res.partner'].create(student._partner_values({
            'name': student.name,
            'email': student.email,
            'phone': student.phone,
            'street': student.street,
            'street2': student.street2,
            'city': student.city,
            'state_id': student.state_id.id,
            'zip': student.zip,
            'country_id': student.country_id.id,
        }))
        student.partner_id = partner

    guardians = env['student.guardian'].search([('partner_id', '=', False)])
    for guardian in guardians:
        guardian.partner_id = env['res.partner'].create({
            'name': guardian.name,
            'email': guardian.email or False,
            'phone': guardian.phone or False,
            'is_company': False,
            'type': 'contact',
        })
