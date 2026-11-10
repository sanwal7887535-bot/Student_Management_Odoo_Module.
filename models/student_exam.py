from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError


class StudentExam(models.Model):
    _name = 'student.exam'
    _description = 'Examination'
    _order = 'exam_date desc, id desc'

    name = fields.Char(required=True, index=True)
    course_id = fields.Many2one('student.course', required=True, ondelete='restrict', index=True)
    academic_year_id = fields.Many2one(
        'student.academic.year', required=True, ondelete='restrict', index=True,
    )
    exam_type = fields.Selection(
        [('quiz', 'Quiz'), ('midterm', 'Midterm'), ('final', 'Final'),
         ('assignment', 'Assignment'), ('other', 'Other')],
        required=True, default='other',
    )
    exam_date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    max_marks = fields.Float(required=True, default=100)
    passing_marks = fields.Float(required=True, default=50)
    teacher_id = fields.Many2one('student.teacher', ondelete='restrict')
    state = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed')],
        default='draft', required=True, index=True,
    )
    result_ids = fields.One2many('student.exam.result', 'exam_id', string='Results')
    result_count = fields.Integer(compute='_compute_result_count')
    notes = fields.Text()

    @api.depends('result_ids')
    def _compute_result_count(self):
        grouped_counts = self.env['student.exam.result']._read_group(
            [('exam_id', 'in', self.ids)],
            groupby=['exam_id'], aggregates=['__count'],
        )
        counts = {exam.id: count for exam, count in grouped_counts}
        for exam in self:
            exam.result_count = counts.get(exam.id, 0)

    @api.onchange('course_id')
    def _onchange_course_id(self):
        if self.course_id and self.env.user.has_group('student_management.group_student_teacher'):
            self.teacher_id = self.env['student.teacher'].search(
                [('user_id', '=', self.env.uid)], limit=1
            )
        elif self.course_id and len(self.course_id.teacher_ids) == 1:
            self.teacher_id = self.course_id.teacher_ids

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('state') == 'confirmed' for vals in vals_list):
            raise UserError(_('Create examinations as drafts and confirm them through the workflow.'))
        if self.env.user.has_group('student_management.group_student_teacher'):
            teacher = self.env['student.teacher'].search(
                [('user_id', '=', self.env.uid)], limit=1
            )
            for vals in vals_list:
                vals['teacher_id'] = teacher.id
        return super().create(vals_list)

    @api.constrains('max_marks', 'passing_marks', 'exam_date', 'academic_year_id')
    def _check_marks_range(self):
        for exam in self:
            if exam.max_marks <= 0:
                raise ValidationError(_('Maximum marks must be greater than zero.'))
            if exam.passing_marks < 0 or exam.passing_marks > exam.max_marks:
                raise ValidationError(_('Passing marks must be between zero and maximum marks.'))
            if not (exam.academic_year_id.date_start <= exam.exam_date <= exam.academic_year_id.date_end):
                raise ValidationError(_('The exam date must fall within its academic year.'))

    @api.constrains('course_id', 'teacher_id')
    def _check_teacher_assignment(self):
        for exam in self:
            if exam.teacher_id and exam.teacher_id not in exam.course_id.teacher_ids:
                raise ValidationError(_('The teacher must be assigned to the exam course.'))
            if self.env.user.has_group('student_management.group_student_teacher'):
                teacher = self.env['student.teacher'].search(
                    [('user_id', '=', self.env.uid)], limit=1
                )
                if not teacher or teacher not in exam.course_id.teacher_ids:
                    raise ValidationError(_('Teachers can only manage exams for their assigned courses.'))
                if exam.teacher_id and exam.teacher_id != teacher:
                    raise ValidationError(_('Teachers can only use their own teacher record.'))

    @api.constrains('state', 'result_ids')
    def _check_confirmed_results(self):
        for exam in self:
            if exam.state == 'confirmed':
                if not exam.result_ids:
                    raise ValidationError(_('Add student results before confirming the exam.'))
                if any(not result.mark_entered for result in exam.result_ids):
                    raise ValidationError(_('Enter marks for every student before confirming the exam.'))

    def action_load_students(self):
        for exam in self:
            if exam.state != 'draft':
                raise UserError(_('Only draft exams can load or update the student list.'))
            enrollments = self.env['student.enrollment'].search([
                ('course_id', '=', exam.course_id.id),
                ('academic_year_id', '=', exam.academic_year_id.id),
                ('state', 'in', ('enrolled', 'completed')),
            ])
            students = enrollments.mapped('student_id')
            if not students:
                raise UserError(_('No enrolled students were found for this course and academic year.'))
            existing_ids = set(exam.result_ids.mapped('student_id').ids)
            rows = [
                Command.create({'student_id': student.id})
                for student in students if student.id not in existing_ids
            ]
            if rows:
                exam.write({'result_ids': rows})
        return True

    def action_confirm(self):
        self.action_load_students()
        if any(not result.mark_entered for result in self.mapped('result_ids')):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Exam roster ready'),
                    'message': _('Enter marks for every student, then confirm the results.'),
                    'type': 'warning',
                },
            }
        self.write({'state': 'confirmed'})

    def action_reset_to_draft(self):
        if not self.env.user.has_group('student_management.group_student_admission'):
            raise UserError(_('Only admission staff or administrators can unlock exam results.'))
        self.write({'state': 'draft'})

    def write(self, vals):
        if vals.get('state') == 'confirmed':
            self.action_load_students()
        if any(exam.state == 'confirmed' for exam in self):
            if vals != {'state': 'draft'} or not self.env.user.has_group(
                'student_management.group_student_admission'
            ):
                raise UserError(_('Reset a confirmed exam to draft before changing it.'))
        return super().write(vals)

    def unlink(self):
        if any(exam.state == 'confirmed' for exam in self):
            raise UserError(_('Confirmed exams cannot be deleted.'))
        return super().unlink()


class StudentExamResult(models.Model):
    _name = 'student.exam.result'
    _description = 'Student Exam Result'
    _order = 'exam_id, student_id'

    exam_id = fields.Many2one('student.exam', required=True, ondelete='cascade', index=True)
    student_id = fields.Many2one('student.student', required=True, ondelete='restrict', index=True)
    course_id = fields.Many2one(
        related='exam_id.course_id', store=True, readonly=True, index=True,
    )
    academic_year_id = fields.Many2one(
        related='exam_id.academic_year_id', store=True, readonly=True, index=True,
    )
    max_marks = fields.Float(related='exam_id.max_marks', store=True, readonly=True)
    passing_marks = fields.Float(related='exam_id.passing_marks', store=True, readonly=True)
    obtained_marks = fields.Float(default=0)
    mark_entered = fields.Boolean(default=False, readonly=True, copy=False)
    percentage = fields.Float(compute='_compute_result', store=True)
    grade = fields.Selection(
        [('a', 'A (90–100%)'), ('b', 'B (80–89%)'), ('c', 'C (70–79%)'),
         ('d', 'D (60–69%)'), ('f', 'F (Below 60%)')],
        compute='_compute_result', store=True,
    )
    result_status = fields.Selection(
        [('pass', 'Pass'), ('fail', 'Fail')], compute='_compute_result', store=True,
    )
    notes = fields.Char()

    _result_unique = models.Constraint(
        'UNIQUE(exam_id, student_id)', 'A student can only have one result per exam.'
    )

    @api.depends('obtained_marks', 'exam_id.max_marks', 'exam_id.passing_marks')
    def _compute_result(self):
        for result in self:
            maximum = result.exam_id.max_marks
            percentage = result.obtained_marks / maximum if maximum else 0
            result.percentage = percentage
            percent_value = percentage * 100
            result.grade = (
                'a' if percent_value >= 90 else 'b' if percent_value >= 80 else
                'c' if percent_value >= 70 else 'd' if percent_value >= 60 else 'f'
            )
            result.result_status = (
                'pass' if result.obtained_marks >= result.exam_id.passing_marks else 'fail'
            )

    @api.constrains('exam_id', 'student_id', 'obtained_marks')
    def _check_student_and_marks(self):
        enrollments = self.env['student.enrollment']._read_group(
            [
                ('student_id', 'in', self.mapped('student_id').ids),
                ('course_id', 'in', self.mapped('exam_id.course_id').ids),
                ('academic_year_id', 'in', self.mapped('exam_id.academic_year_id').ids),
                ('state', 'in', ('enrolled', 'completed')),
            ],
            groupby=['student_id', 'course_id', 'academic_year_id'],
            aggregates=['__count'],
        )
        enrolled_pairs = {
            (student.id, course.id, academic_year.id)
            for student, course, academic_year, _count in enrollments
        }
        for result in self:
            if result.obtained_marks < 0 or result.obtained_marks > result.exam_id.max_marks:
                raise ValidationError(_('Obtained marks must be between zero and maximum marks.'))
            enrollment_key = (
                result.student_id.id,
                result.exam_id.course_id.id,
                result.exam_id.academic_year_id.id,
            )
            if enrollment_key not in enrolled_pairs:
                raise ValidationError(_('The student must be enrolled in the exam course and academic year.'))

    @api.model_create_multi
    def create(self, vals_list):
        if any(
            self.env['student.exam'].browse(vals.get('exam_id')).state == 'confirmed'
            for vals in vals_list
        ):
            raise UserError(_('Confirmed results are locked. Reset the exam to draft first.'))
        for vals in vals_list:
            vals['mark_entered'] = 'obtained_marks' in vals
        return super().create(vals_list)

    def write(self, vals):
        if any(line.exam_id.state == 'confirmed' for line in self):
            raise UserError(_('Confirmed results are locked. Reset the exam to draft first.'))
        vals = vals.copy()
        vals.pop('mark_entered', None)
        if 'obtained_marks' in vals:
            vals = dict(vals, mark_entered=True)
        return super().write(vals)

    def unlink(self):
        if any(line.exam_id.state == 'confirmed' for line in self):
            raise UserError(_('Confirmed results are locked. Reset the exam to draft first.'))
        return super().unlink()
