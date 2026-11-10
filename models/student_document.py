from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StudentDocument(models.Model):
    _name = 'student.document'
    _description = 'Student Document'
    _order = 'student_id, document_date desc, id desc'

    name = fields.Char(required=True, index=True)
    student_id = fields.Many2one('student.student', required=True, ondelete='cascade', index=True)
    document_type = fields.Selection(
        [('admission', 'Admission Form'), ('identity', 'Identity Document'),
         ('certificate', 'Academic Certificate'), ('transfer', 'Transfer Certificate'),
         ('photo', 'Photograph'), ('other', 'Other')],
        required=True, default='other',
    )
    document_date = fields.Date(default=fields.Date.context_today)
    valid_until = fields.Date()
    file_data = fields.Binary(required=True, attachment=True)
    file_name = fields.Char(required=True)
    notes = fields.Text()

    @api.constrains('document_date', 'valid_until')
    def _check_validity(self):
        for document in self:
            if document.valid_until and document.document_date and document.valid_until < document.document_date:
                raise ValidationError(_('The expiry date cannot be before the document date.'))
