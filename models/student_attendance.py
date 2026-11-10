from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError


class StudentAttendanceSession(models.Model):
    _name = 'student.attendance.session'
    _description = 'Attendance Session'
    _order = 'session_date desc, id desc'

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _('New'))
    session_date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    academic_year_id = fields.Many2one(
        'student.academic.year', related='section_id.academic_year_id',
        store=True, readonly=True,
    )
    section_id = fields.Many2one(
        'student.section', required=True, ondelete='restrict', index=True,
    )
    class_id = fields.Many2one(related='section_id.class_id', store=True, readonly=True)
    course_id = fields.Many2one('student.course', ondelete='restrict', index=True)
    teacher_id = fields.Many2one(
        'student.teacher', required=True, ondelete='restrict', index=True,
        default=lambda self: self.env['student.teacher'].search(
            [('user_id', '=', self.env.uid)], limit=1
        ),
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('confirmed', 'Confirmed')],
        default='draft', required=True, index=True,
    )
    attendance_ids = fields.One2many(
        'student.attendance', 'session_id', string='Attendance'
    )
    attendance_count = fields.Integer(compute='_compute_attendance_count')
    notes = fields.Text()

    @api.depends('attendance_ids')
    def _compute_attendance_count(self):
        grouped_counts = self.env['student.attendance']._read_group(
            [('session_id', 'in', self.ids)],
            groupby=['session_id'], aggregates=['__count'],
        )
        counts = {session.id: count for session, count in grouped_counts}
        for session in self:
            session.attendance_count = counts.get(session.id, 0)

    @api.onchange('section_id')
    def _onchange_section_id(self):
        if self.env.user.has_group('student_management.group_student_teacher'):
            self.teacher_id = self.env['student.teacher'].search(
                [('user_id', '=', self.env.uid)], limit=1
            )
        elif self.section_id and self.section_id.teacher_id:
            self.teacher_id = self.section_id.teacher_id

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('state') == 'confirmed' for vals in vals_list):
            raise UserError(_('Create attendance sessions as drafts and confirm them through the workflow.'))
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = sequence.next_by_code('student.attendance.session') or _('New')
            if vals.get('section_id') and not vals.get('teacher_id'):
                section = self.env['student.section'].browse(vals['section_id'])
                vals['teacher_id'] = section.teacher_id.id
            if self.env.user.has_group('student_management.group_student_teacher'):
                teacher = self.env['student.teacher'].search(
                    [('user_id', '=', self.env.uid)], limit=1
                )
                vals['teacher_id'] = teacher.id
        return super().create(vals_list)

    @api.constrains('section_id', 'course_id', 'teacher_id', 'session_date')
    def _check_teacher_assignment(self):
        for session in self:
            teacher = session.teacher_id
            academic_year = session.section_id.academic_year_id
            if not (academic_year.date_start <= session.session_date <= academic_year.date_end):
                raise ValidationError(_('The session date must fall within its academic year.'))
            duplicate = self.search_count([
                ('id', '!=', session.id),
                ('session_date', '=', session.session_date),
                ('section_id', '=', session.section_id.id),
                ('course_id', '=', session.course_id.id or False),
            ])
            if duplicate:
                raise ValidationError(_('An attendance session already exists for this section, course, and date.'))
            if (session.course_id.class_ids
                    and session.section_id.class_id not in session.course_id.class_ids):
                raise ValidationError(_('The selected course is not offered to this section\'s class.'))
            if session.course_id and teacher not in session.course_id.teacher_ids:
                raise ValidationError(_('The teacher must be assigned to the selected course.'))
            if not session.course_id and teacher != session.section_id.teacher_id:
                raise ValidationError(_('The teacher must be assigned to the section.'))
            if self.env.user.has_group('student_management.group_student_teacher'):
                if teacher.user_id != self.env.user:
                    raise ValidationError(_('Teachers can only create sessions under their own account.'))

    @api.constrains('attendance_ids', 'state')
    def _check_confirmed_attendance(self):
        for session in self:
            if session.state == 'confirmed':
                if not session.attendance_ids:
                    raise ValidationError(_('Add attendance records before confirming a session.'))
                if any(line.status == 'unmarked' for line in session.attendance_ids):
                    raise ValidationError(_('Mark every student before confirming the session.'))

    def action_load_students(self):
        for session in self:
            if session.state != 'draft':
                raise UserError(_('Only draft sessions can load or update the roster.'))
            students = session.section_id.student_ids
            if session.course_id:
                enrolled = self.env['student.enrollment'].search([
                    ('course_id', '=', session.course_id.id),
                    ('academic_year_id', '=', session.academic_year_id.id),
                    ('state', '=', 'enrolled'),
                ]).mapped('student_id')
                students &= enrolled
            existing_ids = set(session.attendance_ids.mapped('student_id').ids)
            rows = [
                Command.create({'student_id': student.id, 'status': 'unmarked'})
                for student in students if student.id not in existing_ids
            ]
            if rows:
                session.write({'attendance_ids': rows})
        return True

    def action_confirm(self):
        self.action_load_students()
        if any(line.status == 'unmarked' for line in self.mapped('attendance_ids')):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Attendance roster ready'),
                    'message': _('Mark every student, then confirm the session.'),
                    'type': 'warning',
                },
            }
        self.write({'state': 'confirmed'})

    def action_reset_to_draft(self):
        if not self.env.user.has_group('student_management.group_student_admission'):
            raise UserError(_('Only admission staff or administrators can unlock attendance.'))
        self.write({'state': 'draft'})

    def write(self, vals):
        if vals.get('state') == 'confirmed':
            self.action_load_students()
        if any(session.state == 'confirmed' for session in self):
            if vals != {'state': 'draft'} or not self.env.user.has_group(
                'student_management.group_student_admission'
            ):
                raise UserError(_('Reset a confirmed session to draft before changing it.'))
        return super().write(vals)

    def unlink(self):
        if any(session.state == 'confirmed' for session in self):
            raise UserError(_('Confirmed attendance sessions cannot be deleted.'))
        return super().unlink()


class StudentAttendance(models.Model):
    _name = 'student.attendance'
    _description = 'Student Attendance'
    _order = 'session_id, student_id'

    session_id = fields.Many2one(
        'student.attendance.session', required=True, ondelete='cascade', index=True,
    )
    session_date = fields.Date(
        related='session_id.session_date', store=True, readonly=True, index=True,
    )
    section_id = fields.Many2one(related='session_id.section_id', store=True, readonly=True)
    student_id = fields.Many2one('student.student', required=True, ondelete='restrict', index=True)
    status = fields.Selection(
        [('unmarked', 'Not Marked'), ('present', 'Present'), ('absent', 'Absent'), ('late', 'Late'),
         ('excused', 'Excused')], required=True, default='unmarked', index=True,
    )
    notes = fields.Char()

    _attendance_unique = models.Constraint(
        'UNIQUE(session_id, student_id)',
        'A student can only have one attendance entry per session.',
    )

    @api.constrains('session_id', 'student_id')
    def _check_student_section(self):
        course_attendance = self.filtered(lambda line: line.session_id.course_id)
        enrolled_keys = set()
        if course_attendance:
            enrollments = self.env['student.enrollment']._read_group(
                [
                    ('student_id', 'in', course_attendance.mapped('student_id').ids),
                    ('course_id', 'in', course_attendance.mapped('session_id.course_id').ids),
                    ('academic_year_id', 'in', course_attendance.mapped('session_id.academic_year_id').ids),
                    ('state', '=', 'enrolled'),
                ],
                groupby=['student_id', 'course_id', 'academic_year_id'],
                aggregates=['__count'],
            )
            enrolled_keys = {
                (student.id, course.id, year.id)
                for student, course, year, _count in enrollments
            }
        for attendance in self:
            if attendance.student_id.section_id != attendance.session_id.section_id:
                raise ValidationError(_('The student must belong to the attendance session section.'))
            if attendance.session_id.course_id:
                enrollment_key = (
                    attendance.student_id.id,
                    attendance.session_id.course_id.id,
                    attendance.session_id.academic_year_id.id,
                )
                if enrollment_key not in enrolled_keys:
                    raise ValidationError(_('The student must be enrolled in the attendance session course.'))

    @api.model_create_multi
    def create(self, vals_list):
        if any(
            self.env['student.attendance.session'].browse(vals.get('session_id')).state == 'confirmed'
            for vals in vals_list
        ):
            raise UserError(_('Confirmed attendance is locked. Reset the session to draft first.'))
        return super().create(vals_list)

    def write(self, vals):
        if any(line.session_id.state == 'confirmed' for line in self):
            raise UserError(_('Confirmed attendance is locked. Reset the session to draft first.'))
        return super().write(vals)

    def unlink(self):
        if any(line.session_id.state == 'confirmed' for line in self):
            raise UserError(_('Confirmed attendance is locked. Reset the session to draft first.'))
        return super().unlink()
