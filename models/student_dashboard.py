from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class StudentDashboard(models.TransientModel):
    _name = 'student.dashboard'
    _description = 'Student Management Dashboard'

    student_count = fields.Integer(
        readonly=True,
        groups='student_management.group_student_admission,student_management.group_student_teacher,student_management.group_student_accountant',
    )
    active_class_count = fields.Integer(
        string='Active Classes',
        readonly=True,
        groups='student_management.group_student_admission,student_management.group_student_teacher,student_management.group_student_accountant',
    )
    teacher_count = fields.Integer(
        readonly=True,
        groups='student_management.group_student_admission',
    )
    attendance_today = fields.Float(
        string='Attendance Today (%)',
        readonly=True, digits=(16, 2),
        groups='student_management.group_student_admission,student_management.group_student_teacher',
    )
    average_result = fields.Float(
        string='Average Exam Result (%)',
        readonly=True, digits=(16, 2),
        groups='student_management.group_student_admission,student_management.group_student_teacher',
    )
    outstanding_fees = fields.Monetary(
        readonly=True, currency_field='currency_id',
        groups='student_management.group_student_admission,student_management.group_student_accountant',
    )
    currency_id = fields.Many2one('res.currency', readonly=True)
    dashboard_date = fields.Date(readonly=True)

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        user = self.env.user
        can_admit = user.has_group('student_management.group_student_admission')
        can_teach = user.has_group('student_management.group_student_teacher')
        can_account = user.has_group('student_management.group_student_accountant')
        if not any((can_admit, can_teach, can_account)):
            raise AccessError(_('You are not allowed to open the student dashboard.'))

        if 'student_count' in field_names:
            values['student_count'] = self.env['student.student'].search_count([
                ('active', '=', True),
            ])
        if 'active_class_count' in field_names:
            values['active_class_count'] = self.env['student.class'].search_count([
                ('active', '=', True),
            ])
        if 'teacher_count' in field_names and can_admit:
            values['teacher_count'] = self.env['student.teacher'].search_count([
                ('employment_status', '=', 'active'),
            ])

        if 'attendance_today' in field_names and (can_admit or can_teach):
            today = fields.Date.context_today(self)
            attendance_counts = self.env['student.attendance']._read_group([
                ('session_date', '=', today), ('session_id.state', '=', 'confirmed'),
                ('status', 'in', ('present', 'late', 'absent')),
            ], groupby=['status'], aggregates=['__count'])
            marked_count = sum(count for _status, count in attendance_counts)
            attended_count = sum(
                count for status, count in attendance_counts if status in ('present', 'late')
            )
            values['attendance_today'] = (
                100.0 * attended_count / marked_count if marked_count else 0.0
            )

        if 'average_result' in field_names and (can_admit or can_teach):
            aggregate = self.env['student.exam.result']._read_group([
                ('exam_id.state', '=', 'confirmed'),
            ], aggregates=['percentage:avg'])
            values['average_result'] = (aggregate[0][0] or 0.0) * 100.0 if aggregate else 0.0

        if 'outstanding_fees' in field_names and (can_admit or can_account):
            fee_model = self.env['student.fee']
            aggregate = fee_model._read_group([
                ('invoice_id.state', '=', 'posted'),
                ('invoice_id.payment_state', 'in', ('not_paid', 'partial', 'in_payment')),
                ('company_id', '=', self.env.company.id),
            ], aggregates=['balance_due:sum'])
            values['outstanding_fees'] = aggregate[0][0] or 0.0 if aggregate else 0.0
            values['currency_id'] = self.env.company.currency_id.id

        values['dashboard_date'] = fields.Date.context_today(self)
        return values

    @api.model
    def action_open_dashboard(self):
        record = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Institution Overview'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': record.id,
            'target': 'current',
        }

    def action_refresh(self):
        return self.action_open_dashboard()


class StudentManagementSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    attendance_alerts_enabled = fields.Boolean(
        string='Send Low Attendance Alerts', default=True,
        config_parameter='student_management.attendance_alerts_enabled',
    )
    attendance_alert_threshold = fields.Float(
        string='Low Attendance Threshold (%)', default=75.0,
        config_parameter='student_management.attendance_alert_threshold',
    )
    fee_reminders_enabled = fields.Boolean(
        string='Send Overdue Fee Reminders', default=True,
        config_parameter='student_management.fee_reminders_enabled',
    )
    reminder_repeat_days = fields.Integer(
        string='Reminder Repeat Interval (Days)', default=7,
        config_parameter='student_management.reminder_repeat_days',
    )

    @api.constrains('attendance_alert_threshold', 'reminder_repeat_days')
    def _check_reminder_settings(self):
        for settings in self:
            if not 0 <= settings.attendance_alert_threshold <= 100:
                raise ValidationError(_('The low attendance threshold must be between 0 and 100.'))
            if settings.reminder_repeat_days < 1:
                raise ValidationError(_('The reminder interval must be at least one day.'))
