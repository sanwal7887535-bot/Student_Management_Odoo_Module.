from odoo import api, fields, models


class StudentGuardian(models.Model):
    _name = 'student.guardian'
    _description = 'Student Guardian'
    _order = 'name, id'

    name = fields.Char(string='Guardian Name', required=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', readonly=True, copy=False, index=True,
        groups='student_management.group_student_admission',
    )
    relationship = fields.Selection(
        [('mother', 'Mother'), ('father', 'Father'), ('guardian', 'Guardian'),
         ('other', 'Other')], required=True, default='guardian',
    )
    phone = fields.Char(string='Phone Number', required=True)
    email = fields.Char(string='Email Address')
    emergency_contact = fields.Boolean(string='Emergency Contact')
    student_ids = fields.Many2many(
        'student.student', 'student_guardian_rel', 'guardian_id', 'student_id',
        string='Students',
    )
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('partner_id'):
                vals['partner_id'] = self.env['res.partner'].create({
                    'name': vals.get('name') or '',
                    'email': vals.get('email') or False,
                    'phone': vals.get('phone') or False,
                    'is_company': False,
                    'type': 'contact',
                }).id
        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)
        if {'name', 'email', 'phone'}.intersection(vals):
            for guardian in self.filtered('partner_id'):
                guardian.partner_id.write({
                    'name': guardian.name,
                    'email': guardian.email or False,
                    'phone': guardian.phone or False,
                })
        return result
