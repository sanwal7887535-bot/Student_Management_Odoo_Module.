from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StudentAcademicYear(models.Model):
    _name = 'student.academic.year'
    _description = 'Academic Year'
    _order = 'date_start desc, id desc'

    name = fields.Char(string='Academic Year', required=True)
    date_start = fields.Date(string='Start Date', required=True)
    date_end = fields.Date(string='End Date', required=True)
    active = fields.Boolean(default=True)
    section_ids = fields.One2many('student.section', 'academic_year_id', string='Sections')

    _name_unique = models.Constraint('UNIQUE(name)', 'Academic year name must be unique.')

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for year in self:
            if year.date_end < year.date_start:
                raise ValidationError(_('The end date must be on or after the start date.'))
