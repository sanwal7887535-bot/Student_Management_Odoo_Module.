from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StudentSection(models.Model):
    _name = 'student.section'
    _description = 'Class Section'
    _order = 'class_id, academic_year_id, name'

    name = fields.Char(string='Section', required=True)
    class_id = fields.Many2one('student.class', required=True, ondelete='restrict', index=True)
    academic_year_id = fields.Many2one(
        'student.academic.year', string='Academic Year', required=True,
        ondelete='restrict', index=True,
    )
    teacher_id = fields.Many2one(
        'student.teacher', string='Class Teacher', ondelete='restrict', index=True,
    )
    capacity = fields.Integer(string='Capacity')
    student_ids = fields.One2many('student.student', 'section_id', string='Students')
    student_count = fields.Integer(compute='_compute_student_count', string='Students')

    _section_unique = models.Constraint(
        'UNIQUE(name, class_id, academic_year_id)',
        'Section names must be unique within a class and academic year.',
    )

    @api.depends('student_ids', 'student_ids.active')
    @api.depends_context('active_test')
    def _compute_student_count(self):
        domain = [('section_id', 'in', self.ids)]
        if self.env.context.get('active_test', True):
            domain.append(('active', '=', True))
        grouped_counts = self.env['student.student']._read_group(
            domain, groupby=['section_id'], aggregates=['__count'],
        )
        counts = {section.id: count for section, count in grouped_counts}
        for section in self:
            section.student_count = counts.get(section.id, 0)

    @api.constrains('capacity')
    def _check_capacity(self):
        for section in self:
            if section.capacity < 0:
                raise ValidationError(_('Section capacity cannot be negative.'))
            if section.capacity and section.student_count > section.capacity:
                raise ValidationError(_('Section capacity cannot be lower than its current student count.'))
