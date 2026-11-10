from odoo import api, fields, models, _


class StudentCourse(models.Model):
    _name = 'student.course'
    _description = 'Student Course'

    name = fields.Char(
        string='Course Name',
        required=True
    )

    code = fields.Char(string='Course Code', required=True, index=True)
    credit_hours = fields.Float(string='Credit Hours')
    active = fields.Boolean(default=True)
    class_ids = fields.Many2many(
        'student.class', 'student_course_class_rel', 'course_id', 'class_id',
        string='Classes',
    )
    teacher_ids = fields.Many2many(
        'student.teacher', 'student_course_teacher_rel', 'course_id', 'teacher_id',
        string='Teachers',
    )

    description = fields.Text(
        string='Description'
    )

    student_ids = fields.Many2many(
        'student.student', compute='_compute_student_ids', string='Students'
    )

    enrollment_ids = fields.One2many(
        'student.enrollment', 'course_id', string='Enrollments'
    )

    _code_unique = models.Constraint('UNIQUE(code)', 'Course code must be unique.')

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = sequence.next_by_code('student.course') or _('New')
        return super().create(vals_list)

    @api.depends('enrollment_ids.student_id', 'enrollment_ids.state')
    def _compute_student_ids(self):
        grouped_enrollments = self.env['student.enrollment']._read_group(
            [('course_id', 'in', self.ids), ('state', '=', 'enrolled')],
            groupby=['course_id', 'student_id'], aggregates=['__count'],
        )
        students_by_course = {course.id: set() for course in self}
        for course, student, _count in grouped_enrollments:
            students_by_course[course.id].add(student.id)
        for course in self:
            course.student_ids = self.env['student.student'].browse(
                sorted(students_by_course[course.id])
            )
