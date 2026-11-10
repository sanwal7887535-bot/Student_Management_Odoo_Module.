import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class Student(models.Model):
    _name = 'student.student'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Student'
    _rec_name = 'name'
    _order = 'name, id'

    student_number = fields.Char(
        string='Student ID', required=True, copy=False, readonly=True,
        default=lambda self: _('New'), index=True,
    )
    name = fields.Char(string='Student Name', required=True, index=True, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', readonly=True, copy=False, index=True,
        groups='student_management.group_student_admission,student_management.group_student_accountant',
    )
    image_1920 = fields.Image(string='Student Photo')
    date_of_birth = fields.Date(
        string='Date of Birth', groups='student_management.group_student_admission',
    )
    legacy_age = fields.Integer(string='Legacy Age', readonly=True, copy=False)
    age = fields.Integer(string='Age', compute='_compute_age')
    gender = fields.Selection(
        [('male', 'Male'), ('female', 'Female'), ('other', 'Other')], string='Gender'
    )
    email = fields.Char(
        string='Email Address', required=True, index=True,
        groups='student_management.group_student_admission',
    )
    phone = fields.Char(
        string='Phone Number', required=True,
        groups='student_management.group_student_admission',
    )
    street = fields.Char(string='Street', groups='student_management.group_student_admission')
    street2 = fields.Char(string='Street 2', groups='student_management.group_student_admission')
    city = fields.Char(string='City', groups='student_management.group_student_admission')
    state_id = fields.Many2one(
        'res.country.state', string='State / Province',
        groups='student_management.group_student_admission',
    )
    zip = fields.Char(string='ZIP', groups='student_management.group_student_admission')
    country_id = fields.Many2one(
        'res.country', string='Country', groups='student_management.group_student_admission',
    )
    admission_date = fields.Date(string='Admission Date', default=fields.Date.context_today)
    enrollment_date = fields.Date(string='Enrollment Date', default=fields.Date.context_today)
    academic_status = fields.Selection(
        [('active', 'Active'), ('graduated', 'Graduated'),
         ('suspended', 'Suspended'), ('withdrawn', 'Withdrawn')],
        string='Academic Status', tracking=True,
        required=True, default='active', index=True,
    )
    active = fields.Boolean(string='Active', default=True, index=True)
    notes = fields.Text(string='Notes', groups='student_management.group_student_admission')
    class_id = fields.Many2one(
        'student.class', string='Class', ondelete='restrict', index=True,
    )
    section_id = fields.Many2one(
        'student.section', string='Section', ondelete='restrict', index=True,
        domain="[('class_id', '=', class_id)]",
    )
    guardian_ids = fields.Many2many(
        'student.guardian', 'student_guardian_rel', 'student_id', 'guardian_id',
        string='Guardians', groups='student_management.group_student_admission',
    )
    enrollment_ids = fields.One2many(
        'student.enrollment', 'student_id', string='Course Enrollments'
    )
    course_ids = fields.Many2many(
        'student.course', compute='_compute_course_ids', string='Courses'
    )
    attendance_ids = fields.One2many(
        'student.attendance', 'student_id', string='Attendance',
        groups='student_management.group_student_admission,student_management.group_student_teacher',
    )
    attendance_percentage = fields.Float(
        string='Attendance', compute='_compute_attendance_percentage',
        store=True, index=True,
        groups='student_management.group_student_admission,student_management.group_student_teacher',
    )
    attendance_alert_last_sent = fields.Date(readonly=True, copy=False, index=True)
    exam_result_ids = fields.One2many(
        'student.exam.result', 'student_id', string='Exam Results',
        groups='student_management.group_student_admission,student_management.group_student_teacher',
    )
    fee_ids = fields.One2many(
        'student.fee', 'student_id', string='Fees',
        groups='student_management.group_student_admission,student_management.group_student_accountant',
    )
    document_ids = fields.One2many(
        'student.document', 'student_id', string='Documents',
        groups='student_management.group_student_admission',
    )
    admission_confirmation_sent = fields.Boolean(
        string='Admission Confirmation Sent', readonly=True, copy=False,
    )

    _student_number_unique = models.Constraint(
        'UNIQUE(student_number)', 'Student ID must be unique.'
    )

    @api.depends('date_of_birth', 'legacy_age')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for student in self:
            if student.date_of_birth:
                born = fields.Date.to_date(student.date_of_birth)
                student.age = today.year - born.year - (
                    (today.month, today.day) < (born.month, born.day)
                )
            else:
                student.age = student.legacy_age

    @api.depends('enrollment_ids.course_id', 'enrollment_ids.state')
    def _compute_course_ids(self):
        grouped_enrollments = self.env['student.enrollment']._read_group(
            [('student_id', 'in', self.ids), ('state', '=', 'enrolled')],
            groupby=['student_id', 'course_id'], aggregates=['__count'],
        )
        courses_by_student = {student.id: set() for student in self}
        for student, course, _count in grouped_enrollments:
            courses_by_student[student.id].add(course.id)
        for student in self:
            student.course_ids = self.env['student.course'].browse(
                sorted(courses_by_student[student.id])
            )

    @api.depends('attendance_ids.status', 'attendance_ids.session_id.state')
    def _compute_attendance_percentage(self):
        grouped_attendance = self.env['student.attendance']._read_group(
            [
                ('student_id', 'in', self.ids),
                ('session_id.state', '=', 'confirmed'),
                ('status', 'in', ('present', 'late', 'absent')),
            ],
            groupby=['student_id', 'status'], aggregates=['__count'],
        )
        totals_by_student = {student.id: [0, 0] for student in self}
        for student, status, count in grouped_attendance:
            totals = totals_by_student[student.id]
            totals[1] += count
            if status in ('present', 'late'):
                totals[0] += count
        for student in self:
            attended, marked = totals_by_student[student.id]
            student.attendance_percentage = attended / marked if marked else 0.0

    @api.onchange('email')
    def _onchange_email(self):
        if self.email:
            self.email = self.email.strip().lower()

    @api.onchange('phone')
    def _onchange_phone(self):
        if self.phone:
            self.phone = self.phone.strip()

    @api.onchange('class_id')
    def _onchange_class_id(self):
        if self.section_id and self.section_id.class_id != self.class_id:
            self.section_id = False

    @api.onchange('section_id')
    def _onchange_section_id(self):
        if self.section_id:
            self.class_id = self.section_id.class_id

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('student_number', _('New')) == _('New'):
                vals['student_number'] = sequence.next_by_code('student.student') or _('New')
            if vals.get('email'):
                vals['email'] = vals['email'].strip().lower()
            if vals.get('phone'):
                vals['phone'] = vals['phone'].strip()
            if vals.get('section_id') and not vals.get('class_id'):
                section = self.env['student.section'].browse(vals['section_id'])
                vals['class_id'] = section.class_id.id
            if not vals.get('partner_id'):
                vals['partner_id'] = self.env['res.partner'].create(
                    self._partner_values(vals)
                ).id
        return super().create(vals_list)

    def write(self, vals):
        vals = vals.copy()
        if vals.get('email'):
            vals['email'] = vals['email'].strip().lower()
        if vals.get('phone'):
            vals['phone'] = vals['phone'].strip()
        if 'section_id' in vals:
            section = self.env['student.section'].browse(vals['section_id'])
            if section:
                vals['class_id'] = section.class_id.id
        result = super().write(vals)
        partner_fields = {
            'name', 'email', 'phone', 'street', 'street2', 'city',
            'state_id', 'zip', 'country_id',
        }
        if partner_fields.intersection(vals):
            for student in self.filtered('partner_id'):
                partner_vals = {
                    'name': student.name,
                    'email': student.email or False,
                    'phone': student.phone or False,
                    'street': student.street or False,
                    'street2': student.street2 or False,
                    'city': student.city or False,
                    'state_id': student.state_id.id or False,
                    'zip': student.zip or False,
                    'country_id': student.country_id.id or False,
                }
                student.partner_id.write(partner_vals)
        return result

    @staticmethod
    def _partner_values(values):
        return {
            'name': values.get('name') or '',
            'email': values.get('email') or False,
            'phone': values.get('phone') or False,
            'street': values.get('street') or False,
            'street2': values.get('street2') or False,
            'city': values.get('city') or False,
            'state_id': values.get('state_id') or False,
            'zip': values.get('zip') or False,
            'country_id': values.get('country_id') or False,
            'is_company': False,
            'type': 'contact',
        }

    def action_send_admission_confirmation(self):
        if not self.env.user.has_group('student_management.group_student_admission'):
            raise UserError(_('Only admission staff can send admission confirmations.'))
        template = self.env.ref(
            'student_management.mail_template_admission_confirmation',
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(_('The admission confirmation email template is missing.'))
        for student in self:
            if not student.admission_confirmation_sent:
                template.send_mail(student.id, force_send=False)
                student.admission_confirmation_sent = True
        return True

    @api.constrains('date_of_birth')
    def _check_date_of_birth(self):
        today = fields.Date.context_today(self)
        for student in self:
            if student.date_of_birth and student.date_of_birth > today:
                raise ValidationError(_('Date of birth cannot be in the future.'))

    @api.constrains('email')
    def _check_email(self):
        for student in self:
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", (student.email or '').strip()):
                raise ValidationError(_('Enter a valid email address.'))
            duplicate = self.search([
                ('id', '!=', student.id), ('email', '=ilike', student.email.strip()),
            ], limit=1)
            if duplicate:
                raise ValidationError(_('A student with this email address already exists.'))

    @api.constrains('section_id', 'class_id')
    def _check_section_class(self):
        for student in self:
            if student.section_id and student.class_id != student.section_id.class_id:
                raise ValidationError(_('The selected section must belong to the selected class.'))
            if (student.section_id and student.section_id.capacity
                    and student.section_id.student_count > student.section_id.capacity):
                raise ValidationError(_('The selected section has reached its capacity.'))

    def action_archive(self):
        self.write({'active': False})

    def action_unarchive(self):
        self.write({'active': True})

    def unlink(self):
        raise UserError(_('Student records must be archived so their history is preserved.'))

    @api.model
    def _cron_send_low_attendance_alerts(self):
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param('student_management.attendance_alerts_enabled', 'True') != 'True':
            return
        try:
            threshold = float(params.get_param(
                'student_management.attendance_alert_threshold', '75'
            ))
        except (TypeError, ValueError):
            threshold = 75.0
        threshold = min(max(threshold, 0.0), 100.0) / 100.0
        try:
            repeat_days = max(1, int(params.get_param(
                'student_management.reminder_repeat_days', '7'
            )))
        except (TypeError, ValueError):
            repeat_days = 7
        today = fields.Date.context_today(self)
        cutoff = fields.Date.subtract(today, days=repeat_days)
        students = self.search([
            ('active', '=', True), ('academic_status', '=', 'active'),
            ('attendance_ids.session_id.state', '=', 'confirmed'),
            ('attendance_ids.session_date', '<=', today),
            ('attendance_ids.status', 'in', ('present', 'late', 'absent')),
            ('attendance_percentage', '<', threshold),
            '|', ('attendance_alert_last_sent', '=', False),
            ('attendance_alert_last_sent', '<=', cutoff),
        ])
        template = self.env.ref(
            'student_management.mail_template_low_attendance_alert',
            raise_if_not_found=False,
        )
        if not template:
            return
        for student in students:
            recipients = list(dict.fromkeys(
                student.guardian_ids.filtered('email').mapped('email')
            ))
            if not recipients and student.email:
                recipients = [student.email]
            if not recipients:
                continue
            for recipient in recipients:
                template.send_mail(student.id, force_send=False, email_values={
                    'email_to': recipient,
                })
            student.attendance_alert_last_sent = today
