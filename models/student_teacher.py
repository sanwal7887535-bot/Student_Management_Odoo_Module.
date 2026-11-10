from odoo import api, fields, models, _


class StudentTeacher(models.Model):
    _name = 'student.teacher'
    _description = 'Teacher'
    _order = 'name, id'

    teacher_number = fields.Char(
        string='Teacher ID', required=True, readonly=True, copy=False,
        default=lambda self: _('New'), index=True,
    )
    name = fields.Char(required=True, index=True)
    user_id = fields.Many2one(
        'res.users', string='Odoo User', domain=[('share', '=', False)],
        ondelete='restrict', index=True,
    )
    email = fields.Char()
    phone = fields.Char()
    qualification = fields.Char()
    specialization = fields.Char()
    joining_date = fields.Date()
    employment_status = fields.Selection(
        [('active', 'Active'), ('on_leave', 'On Leave'), ('inactive', 'Inactive')],
        default='active', required=True,
    )
    section_ids = fields.One2many('student.section', 'teacher_id', string='Sections')
    course_ids = fields.Many2many(
        'student.course', 'student_course_teacher_rel', 'teacher_id', 'course_id',
        string='Courses',
    )

    _teacher_number_unique = models.Constraint(
        'UNIQUE(teacher_number)', 'Teacher ID must be unique.'
    )
    _user_unique = models.Constraint(
        'UNIQUE(user_id)', 'An Odoo user can only be linked to one teacher.'
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('teacher_number', _('New')) == _('New'):
                vals['teacher_number'] = sequence.next_by_code('student.teacher') or _('New')
        return super().create(vals_list)
