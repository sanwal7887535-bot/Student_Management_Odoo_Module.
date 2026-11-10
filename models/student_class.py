from odoo import models, fields


class StudentClass(models.Model):
    _name = 'student.class'
    _description = 'Student Class'

    name = fields.Char(
        string='Class Name',
        required=True
    )

    description = fields.Text(
        string='Description'
    )

    student_ids = fields.One2many(
        'student.student',
        'class_id',
        string='Students'
    )
    section_ids = fields.One2many('student.section', 'class_id', string='Sections')
    course_ids = fields.Many2many(
        'student.course', 'student_course_class_rel', 'class_id', 'course_id',
        string='Courses',
    )
    active = fields.Boolean(default=True)
