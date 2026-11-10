from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StudentEnrollment(models.Model):
    _name = 'student.enrollment'
    _description = 'Student Course Enrollment'
    _order = 'academic_year_id desc, student_id, course_id'

    @api.model_create_multi
    def create(self, vals_list):
        if any(not vals.get('academic_year_id') for vals in vals_list):
            raise ValidationError(_('Select an academic year for each new course enrollment.'))
        return super().create(vals_list)

    student_id = fields.Many2one(
        'student.student', required=True, ondelete='cascade', index=True
    )
    course_id = fields.Many2one(
        'student.course', required=True, ondelete='restrict', index=True
    )
    academic_year_id = fields.Many2one(
        'student.academic.year', string='Academic Year',
        ondelete='restrict', index=True,
    )
    enrollment_date = fields.Date(default=fields.Date.context_today, required=True)
    state = fields.Selection(
        [('enrolled', 'Enrolled'), ('completed', 'Completed'),
         ('withdrawn', 'Withdrawn')], default='enrolled', required=True, index=True,
    )
    notes = fields.Text()

    @api.constrains('student_id', 'course_id', 'academic_year_id')
    def _check_unique_enrollment(self):
        candidate_keys = []
        for enrollment in self:
            candidate_keys.append((
                enrollment.student_id.id,
                enrollment.course_id.id,
                enrollment.academic_year_id.id or False,
            ))
        if len(candidate_keys) != len(set(candidate_keys)):
            raise ValidationError(_('This student is already enrolled in that course for this academic year.'))

        existing = self.search([
            ('id', 'not in', self.ids),
            ('student_id', 'in', list({key[0] for key in candidate_keys})),
            ('course_id', 'in', list({key[1] for key in candidate_keys})),
            ('academic_year_id', 'in', list({key[2] for key in candidate_keys})),
        ])
        existing_keys = {
            (enrollment.student_id.id, enrollment.course_id.id,
             enrollment.academic_year_id.id or False)
            for enrollment in existing
        }
        if existing_keys.intersection(candidate_keys):
            raise ValidationError(_('This student is already enrolled in that course for this academic year.'))

        for enrollment in self:
            if (enrollment.course_id.class_ids
                    and enrollment.student_id.class_id not in enrollment.course_id.class_ids):
                raise ValidationError(_('This course is not assigned to the student\'s class.'))
            if (enrollment.student_id.section_id and enrollment.academic_year_id
                    != enrollment.student_id.section_id.academic_year_id):
                raise ValidationError(_('The enrollment year must match the student\'s assigned section year.'))
