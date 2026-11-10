from datetime import date
from unittest.mock import patch
from uuid import uuid4

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestStudentWorkflows(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.academic_year = cls.env['student.academic.year'].create({
            'name': f'Test Year {today.year}',
            'date_start': date(today.year, 1, 1),
            'date_end': date(today.year, 12, 31),
        })
        cls.student_class = cls.env['student.class'].create({'name': 'Test Class'})
        cls.teacher = cls.env['student.teacher'].create({'name': 'Test Teacher'})
        cls.section = cls.env['student.section'].create({
            'name': 'A',
            'class_id': cls.student_class.id,
            'academic_year_id': cls.academic_year.id,
            'teacher_id': cls.teacher.id,
            'capacity': 20,
        })
        cls.course = cls.env['student.course'].create({
            'name': 'Test Course',
            'class_ids': [Command.set(cls.student_class.ids)],
            'teacher_ids': [Command.set(cls.teacher.ids)],
        })

    def _student(self, name='Test Student'):
        return self.env['student.student'].create({
            'name': name,
            'email': f'{uuid4().hex}@example.test',
            'phone': '5550100',
            'class_id': self.student_class.id,
            'section_id': self.section.id,
        })

    def test_student_identity_normalization_and_partner_sync(self):
        student = self._student()
        self.assertTrue(student.student_number.startswith('STU-'))
        self.assertEqual(student.email, student.email.lower())
        self.assertEqual(student.partner_id.name, student.name)

        student.write({'name': 'Updated Student', 'phone': '5550199'})
        self.assertEqual(student.partner_id.name, 'Updated Student')
        self.assertEqual(student.partner_id.phone, '5550199')

    def test_student_age_is_current_and_records_are_archived(self):
        today = fields.Date.today()
        student = self._student()
        student.write({'date_of_birth': date(today.year - 18, today.month, min(today.day, 28))})
        self.assertEqual(student.age, 18)

        legacy_student = self.env['student.student'].create({
            'name': 'Legacy Age Student',
            'email': f'{uuid4().hex}@example.test',
            'phone': '5550100',
            'legacy_age': 22,
        })
        self.assertEqual(legacy_student.age, 22)

        with self.assertRaises(UserError):
            student.unlink()
        student.action_archive()
        self.assertFalse(student.active)

    def test_student_rejects_invalid_duplicate_email_and_future_birth_date(self):
        with self.assertRaises(ValidationError):
            self.env['student.student'].create({
                'name': 'Invalid Email Student',
                'email': 'not-an-email',
                'phone': '5550100',
            })

        existing = self._student('Existing Student')
        with self.assertRaises(ValidationError):
            self.env['student.student'].create({
                'name': 'Duplicate Email Student',
                'email': existing.email.upper(),
                'phone': '5550100',
            })

        with self.assertRaises(ValidationError):
            self.env['student.student'].create({
                'name': 'Future Birth Date Student',
                'email': f'{uuid4().hex}@example.test',
                'phone': '5550100',
                'date_of_birth': date(fields.Date.today().year + 1, 1, 1),
            })

    def test_academic_year_rejects_reversed_dates(self):
        with self.assertRaises(ValidationError):
            self.env['student.academic.year'].create({
                'name': f'Reversed {uuid4().hex}',
                'date_start': date(2026, 12, 31),
                'date_end': date(2026, 1, 1),
            })

    def test_fee_discount_calculation_and_validation(self):
        fee_model = self.env['student.fee']
        fee = fee_model.new({'amount': 1500, 'discount_amount': 250})
        fee._compute_amount_total()
        self.assertEqual(fee.amount_total, 1250)

        invalid_fee = fee_model.new({'amount': 1500, 'discount_amount': 1501})
        with self.assertRaises(ValidationError):
            invalid_fee._check_fee_amount_and_class()

    def test_reports_and_notification_jobs_are_registered(self):
        report_ids = (
            'action_report_student_profile',
            'action_report_student_result_card',
            'action_report_student_fee_statement',
            'action_report_attendance_register',
            'action_report_exam_results',
        )
        for report_xmlid in report_ids:
            report = self.env.ref(f'student_management.{report_xmlid}')
            self.assertEqual(report.report_type, 'qweb-pdf')
        self.assertTrue(self.env.ref('student_management.ir_cron_student_low_attendance_alerts'))
        self.assertTrue(self.env.ref('student_management.ir_cron_student_overdue_fee_reminders'))

    def test_low_attendance_alert_is_cooled_down(self):
        student = self._student('Low Attendance Student')
        guardian = self.env['student.guardian'].create({
            'name': 'Attendance Guardian',
            'relationship': 'guardian',
            'phone': '5550200',
            'email': f'{uuid4().hex}@example.test',
            'student_ids': [Command.set(student.ids)],
        })
        today = fields.Date.today()
        session = self.env['student.attendance.session'].create({
            'session_date': today,
            'section_id': self.section.id,
            'teacher_id': self.teacher.id,
        })
        self.env['student.attendance'].create({
            'session_id': session.id,
            'student_id': student.id,
            'status': 'absent',
        })
        session.write({'state': 'confirmed'})

        params = self.env['ir.config_parameter'].sudo()
        params.set_param('student_management.attendance_alerts_enabled', True)
        params.set_param('student_management.attendance_alert_threshold', 75)
        params.set_param('student_management.reminder_repeat_days', 7)
        template = self.env.ref('student_management.mail_template_low_attendance_alert')
        with patch.object(type(template), 'send_mail', return_value=1) as send_mail:
            self.env['student.student']._cron_send_low_attendance_alerts()
            self.env['student.student']._cron_send_low_attendance_alerts()

        self.assertEqual(send_mail.call_count, 1)
        self.assertEqual(send_mail.call_args.kwargs['email_values']['email_to'], guardian.email)
        self.assertEqual(student.attendance_alert_last_sent, today)

    def test_exam_result_enrollment_grade_and_confirmation_lock(self):
        student = self._student()
        self.env['student.enrollment'].create({
            'student_id': student.id,
            'course_id': self.course.id,
            'academic_year_id': self.academic_year.id,
        })
        exam = self.env['student.exam'].create({
            'name': 'Workflow Exam',
            'course_id': self.course.id,
            'academic_year_id': self.academic_year.id,
            'exam_date': fields.Date.today(),
            'max_marks': 100,
            'passing_marks': 50,
        })
        exam.action_load_students()
        result = exam.result_ids.filtered(lambda line: line.student_id == student)
        self.assertEqual(len(result), 1)
        result.write({'obtained_marks': 92})
        self.assertEqual(result.grade, 'a')
        self.assertEqual(result.result_status, 'pass')
        self.assertAlmostEqual(result.percentage, 0.92)
        self.assertTrue(result.mark_entered)

        exam.action_confirm()
        self.assertEqual(exam.state, 'confirmed')
        with self.assertRaises(UserError):
            result.write({'obtained_marks': 80})

    def test_exam_mark_state_cannot_be_forged_through_create_or_write(self):
        student = self._student('Unmarked Exam Student')
        self.env['student.enrollment'].create({
            'student_id': student.id,
            'course_id': self.course.id,
            'academic_year_id': self.academic_year.id,
        })
        exam = self.env['student.exam'].create({
            'name': 'Mark State Exam',
            'course_id': self.course.id,
            'academic_year_id': self.academic_year.id,
            'exam_date': fields.Date.today(),
        })
        result = self.env['student.exam.result'].create({
            'exam_id': exam.id,
            'student_id': student.id,
            'mark_entered': True,
        })
        self.assertFalse(result.mark_entered)
        result.write({'mark_entered': True})
        self.assertFalse(result.mark_entered)
        exam.action_confirm()
        self.assertEqual(exam.state, 'draft')

        with self.assertRaises(UserError):
            self.env['student.exam'].create({
                'name': 'Directly Confirmed Exam',
                'course_id': self.course.id,
                'academic_year_id': self.academic_year.id,
                'exam_date': fields.Date.today(),
                'state': 'confirmed',
            })

    def test_attendance_confirmation_and_percentage(self):
        student = self._student()
        statuses = ('present', 'present', 'absent', 'excused')
        for offset, status in enumerate(statuses):
            session = self.env['student.attendance.session'].create({
                'session_date': date(fields.Date.today().year, fields.Date.today().month, offset + 1),
                'section_id': self.section.id,
                'teacher_id': self.teacher.id,
            })

        with self.assertRaises(UserError):
            self.env['student.attendance.session'].create({
                'session_date': fields.Date.today(),
                'section_id': self.section.id,
                'teacher_id': self.teacher.id,
                'state': 'confirmed',
            })
            self.env['student.attendance'].create({
                'session_id': session.id,
                'student_id': student.id,
                'status': status,
            })
            session.write({'state': 'confirmed'})

        self.assertAlmostEqual(student.attendance_percentage, 2 / 3, places=2)
        with self.assertRaises(UserError):
            self.env['student.attendance'].create({
                'session_id': session.id,
                'student_id': student.id,
                'status': 'present',
            })

    def test_teacher_record_rule_limits_students_to_assignment(self):
        teacher_group = self.env.ref('student_management.group_student_teacher')
        teacher_user = self.env['res.users'].create({
            'name': 'Assigned Teacher User',
            'login': f'teacher_{uuid4().hex}',
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id, teacher_group.id,
            ])],
        })
        self.teacher.user_id = teacher_user
        assigned_student = self._student('Assigned Student')
        other_teacher = self.env['student.teacher'].create({'name': 'Other Teacher'})
        other_class = self.env['student.class'].create({'name': f'Other {uuid4().hex}'})
        other_section = self.env['student.section'].create({
            'name': 'B',
            'class_id': other_class.id,
            'academic_year_id': self.academic_year.id,
            'teacher_id': other_teacher.id,
        })
        other_student = self.env['student.student'].create({
            'name': 'Unassigned Student',
            'email': f'{uuid4().hex}@example.test',
            'phone': '5550101',
            'class_id': other_class.id,
            'section_id': other_section.id,
        })

        visible_ids = self.env['student.student'].with_user(teacher_user).search([
            ('id', 'in', [assigned_student.id, other_student.id]),
        ]).ids
        self.assertEqual(visible_ids, [assigned_student.id])
        with self.assertRaises(UserError):
            assigned_student.with_user(teacher_user).action_send_admission_confirmation()
        self.assertFalse(
            self.env['student.fee'].with_user(teacher_user).check_access_rights(
                'read', raise_exception=False
            )
        )
        with self.assertRaises(AccessError):
            assigned_student.with_user(teacher_user).read(['email'])

    def test_teacher_record_rules_limit_attendance_and_exams(self):
        teacher_group = self.env.ref('student_management.group_student_teacher')
        teacher_user = self.env['res.users'].create({
            'name': 'Academic Scope Teacher',
            'login': f'academic_teacher_{uuid4().hex}',
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id, teacher_group.id,
            ])],
        })
        self.teacher.user_id = teacher_user
        other_teacher = self.env['student.teacher'].create({'name': 'Unassigned Teacher'})
        other_class = self.env['student.class'].create({'name': f'Other Class {uuid4().hex}'})
        other_section = self.env['student.section'].create({
            'name': 'Other Section',
            'class_id': other_class.id,
            'academic_year_id': self.academic_year.id,
            'teacher_id': other_teacher.id,
        })
        other_course = self.env['student.course'].create({
            'name': f'Other Course {uuid4().hex}',
            'class_ids': [Command.set(other_class.ids)],
            'teacher_ids': [Command.set(other_teacher.ids)],
        })
        today = fields.Date.today()
        assigned_session = self.env['student.attendance.session'].create({
            'session_date': today,
            'section_id': self.section.id,
            'teacher_id': self.teacher.id,
        })
        other_session = self.env['student.attendance.session'].create({
            'session_date': today,
            'section_id': other_section.id,
            'teacher_id': other_teacher.id,
        })
        assigned_exam = self.env['student.exam'].create({
            'name': 'Assigned Exam',
            'course_id': self.course.id,
            'academic_year_id': self.academic_year.id,
            'exam_date': today,
        })
        other_exam = self.env['student.exam'].create({
            'name': 'Other Exam',
            'course_id': other_course.id,
            'academic_year_id': self.academic_year.id,
            'exam_date': today,
        })

        visible_sessions = self.env['student.attendance.session'].with_user(teacher_user).search([
            ('id', 'in', [assigned_session.id, other_session.id]),
        ])
        visible_exams = self.env['student.exam'].with_user(teacher_user).search([
            ('id', 'in', [assigned_exam.id, other_exam.id]),
        ])
        self.assertEqual(visible_sessions.ids, [assigned_session.id])
        self.assertEqual(visible_exams.ids, [assigned_exam.id])

    def test_accountant_creates_and_posts_fee_invoice(self):
        company = self.env.company
        account_model = self.env['account.account'].with_company(company)

        def make_account(account_type, reconcile=False):
            return account_model.create({
                'name': f'Test {account_type} {uuid4().hex[:8]}',
                'code': f'{uuid4().int % 10**6:06d}',
                'account_type': account_type,
                'reconcile': reconcile,
                'company_ids': [Command.set(company.ids)],
            })

        income_account = make_account('income')
        receivable_account = make_account('asset_receivable', reconcile=True)
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', company.id),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].create({
                'name': f'Test Sales {uuid4().hex[:6]}',
                'code': f'S{uuid4().hex[:4].upper()}',
                'type': 'sale',
                'company_id': company.id,
            })
        student = self._student('Fee Invoice Student')
        student.partner_id.with_company(company).property_account_receivable_id = receivable_account
        structure = self.env['student.fee.structure'].create({
            'name': f'Test Tuition {uuid4().hex[:8]}',
            'amount': 125.0,
            'company_id': company.id,
            'account_id': income_account.id,
        })
        fee = self.env['student.fee'].create({
            'student_id': student.id,
            'fee_structure_id': structure.id,
            'academic_year_id': self.academic_year.id,
            'period': 'Test period',
            'due_date': fields.Date.subtract(fields.Date.today(), days=1),
            'amount': 125.0,
        })

        accountant_group = self.env.ref('student_management.group_student_accountant')
        accounting_group = self.env.ref('account.group_account_invoice')
        accountant = self.env['res.users'].create({
            'name': 'Fee Invoice Accountant',
            'login': f'fee_accountant_{uuid4().hex}',
            'company_id': company.id,
            'company_ids': [Command.set(company.ids)],
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                accountant_group.id,
                accounting_group.id,
            ])],
        })

        fee.with_user(accountant).action_create_invoice()

        self.assertTrue(fee.invoice_id)
        self.assertEqual(fee.invoice_id.state, 'posted')
        self.assertEqual(fee.invoice_id.move_type, 'out_invoice')
        self.assertEqual(fee.invoice_id.journal_id, journal)
        self.assertEqual(fee.invoice_id.amount_total, 125.0)
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('student_management.fee_reminders_enabled', True)
        params.set_param('student_management.reminder_repeat_days', 7)
        template = self.env.ref('student_management.mail_template_overdue_fee_reminder')
        with patch.object(type(template), 'send_mail', return_value=1) as send_mail:
            self.env['student.fee']._cron_send_overdue_reminders()
            self.env['student.fee']._cron_send_overdue_reminders()
        self.assertEqual(send_mail.call_count, 1)
        self.assertEqual(fee.reminder_last_sent, fields.Date.today())
        with self.assertRaises(UserError):
            fee.write({'invoice_id': fee.invoice_id.id})
        with self.assertRaises(UserError):
            fee.write({'amount': 150.0})

    def test_fee_records_are_limited_to_allowed_companies(self):
        company = self.env['res.company'].create({
            'name': f'Other Company {uuid4().hex[:8]}',
        })
        income_account = self.env['account.account'].with_company(company).create({
            'name': 'Other Company Tuition Income',
            'code': f'{uuid4().int % 10**6:06d}',
            'account_type': 'income',
            'company_ids': [Command.set(company.ids)],
        })
        structure = self.env['student.fee.structure'].create({
            'name': f'Other Company Tuition {uuid4().hex[:8]}',
            'amount': 100,
            'company_id': company.id,
            'account_id': income_account.id,
        })
        student = self._student('Other Company Fee Student')
        fee = self.env['student.fee'].create({
            'student_id': student.id,
            'fee_structure_id': structure.id,
            'academic_year_id': self.academic_year.id,
            'period': 'Other company period',
            'due_date': fields.Date.today(),
            'amount': 100,
        })
        accountant = self.env['res.users'].create({
            'name': 'Single Company Fee Accountant',
            'login': f'single_company_accountant_{uuid4().hex}',
            'company_id': self.env.company.id,
            'company_ids': [Command.set(self.env.company.ids)],
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('student_management.group_student_accountant').id,
            ])],
        })
        with self.assertRaises(AccessError):
            fee.with_user(accountant).check_access_rule('read')
