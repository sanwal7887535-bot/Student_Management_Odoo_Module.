from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError


class StudentFeeStructure(models.Model):
    _name = 'student.fee.structure'
    _description = 'Student Fee Structure'
    _order = 'name, id'

    name = fields.Char(required=True, index=True)
    fee_type = fields.Selection(
        [('tuition', 'Tuition'), ('admission', 'Admission'), ('exam', 'Examination'),
         ('transport', 'Transport'), ('other', 'Other')],
        required=True, default='tuition',
    )
    amount = fields.Monetary(required=True, currency_field='currency_id')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, index=True,
    )
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    account_id = fields.Many2one(
        'account.account', required=True, check_company=True, ondelete='restrict',
        domain="[('account_type', 'in', ['income', 'income_other']), ('company_ids', 'in', company_id)]",
    )
    tax_ids = fields.Many2many('account.tax', string='Taxes', check_company=True)
    class_ids = fields.Many2many(
        'student.class', 'student_fee_structure_class_rel',
        'structure_id', 'class_id', string='Applicable Classes',
    )
    active = fields.Boolean(default=True)
    description = fields.Text()

    @api.constrains('amount', 'account_id', 'company_id')
    def _check_fee_configuration(self):
        for structure in self:
            if structure.amount <= 0:
                raise ValidationError(_('Fee amount must be greater than zero.'))
            if structure.account_id and structure.account_id.company_ids and structure.company_id not in structure.account_id.company_ids:
                raise ValidationError(_('The income account must be available to the selected company.'))


class StudentFee(models.Model):
    _name = 'student.fee'
    _description = 'Student Fee'
    _order = 'due_date, student_id, id'

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _('New'), index=True)
    student_id = fields.Many2one('student.student', required=True, ondelete='restrict', index=True)
    fee_structure_id = fields.Many2one(
        'student.fee.structure', required=True, ondelete='restrict', index=True,
    )
    academic_year_id = fields.Many2one(
        'student.academic.year', required=True, ondelete='restrict', index=True,
    )
    period = fields.Char(string='Billing Period', required=True, help='For example, September 2026 or Annual.')
    partner_id = fields.Many2one('res.partner', required=True, ondelete='restrict', index=True)
    due_date = fields.Date(required=True, index=True)
    company_id = fields.Many2one(
        related='fee_structure_id.company_id', store=True, readonly=True, index=True,
    )
    currency_id = fields.Many2one(related='fee_structure_id.currency_id', readonly=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    discount_amount = fields.Monetary(currency_field='currency_id', default=0)
    amount_total = fields.Monetary(
        string='Fee Subtotal', compute='_compute_amount_total', store=True,
        currency_field='currency_id',
    )
    invoice_id = fields.Many2one(
        'account.move', readonly=True, copy=False, ondelete='restrict', index=True,
    )
    invoice_total = fields.Monetary(
        related='invoice_id.amount_total', string='Invoice Total', readonly=True,
        currency_field='currency_id',
    )
    invoice_payment_state = fields.Selection(
        related='invoice_id.payment_state', store=True, readonly=True, index=True,
    )
    balance_due = fields.Monetary(
        related='invoice_id.amount_residual', store=True, readonly=True,
        currency_field='currency_id', index=True,
    )
    reminder_last_sent = fields.Date(readonly=True, copy=False, index=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('invoiced', 'Invoiced'), ('in_payment', 'In Payment'),
         ('partial', 'Partially Paid'), ('paid', 'Paid'), ('overdue', 'Overdue'),
         ('cancelled', 'Cancelled')], compute='_compute_state', string='Status',
    )
    notes = fields.Text()

    _fee_number_unique = models.Constraint('UNIQUE(name)', 'Fee reference must be unique.')
    _fee_year_unique = models.Constraint(
        'UNIQUE(student_id, fee_structure_id, academic_year_id, period)',
        'A fee of this type can only be issued once per student, period, and academic year.',
    )

    @api.depends('amount', 'discount_amount')
    def _compute_amount_total(self):
        for fee in self:
            fee.amount_total = fee.amount - fee.discount_amount

    @api.depends('invoice_id.state', 'invoice_id.payment_state', 'due_date')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for fee in self:
            invoice = fee.invoice_id
            if not invoice:
                fee.state = 'draft'
            elif invoice.state == 'cancel':
                fee.state = 'cancelled'
            elif invoice.state == 'draft':
                fee.state = 'draft'
            elif invoice.payment_state == 'paid':
                fee.state = 'paid'
            elif invoice.payment_state == 'in_payment':
                fee.state = 'in_payment'
            elif invoice.payment_state == 'partial':
                fee.state = 'partial'
            elif fee.due_date and fee.due_date < today:
                fee.state = 'overdue'
            else:
                fee.state = 'invoiced'

    @api.onchange('student_id')
    def _onchange_student_id(self):
        if self.student_id:
            self.partner_id = self.student_id.partner_id

    @api.onchange('fee_structure_id')
    def _onchange_fee_structure_id(self):
        if self.fee_structure_id:
            self.amount = self.fee_structure_id.amount

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('invoice_id'):
                raise UserError(_('Link fee invoices through the student fee invoicing workflow.'))
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = sequence.next_by_code('student.fee') or _('New')
            if vals.get('fee_structure_id') and 'amount' not in vals:
                structure = self.env['student.fee.structure'].browse(vals['fee_structure_id'])
                vals['amount'] = structure.amount
            if vals.get('student_id') and not vals.get('partner_id'):
                student = self.env['student.student'].browse(vals['student_id'])
                vals['partner_id'] = student.partner_id.id
        return super().create(vals_list)

    @api.constrains('amount', 'discount_amount', 'fee_structure_id', 'student_id')
    def _check_fee_amount_and_class(self):
        for fee in self:
            if fee.amount <= 0 or fee.discount_amount < 0 or fee.discount_amount > fee.amount:
                raise ValidationError(_('The fee amount must be positive and discount cannot exceed the fee.'))
            if (fee.fee_structure_id.class_ids
                    and fee.student_id.class_id not in fee.fee_structure_id.class_ids):
                raise ValidationError(_('This fee structure does not apply to the student\'s class.'))

    def action_create_invoice(self):
        self.ensure_one()
        if not self.env.user.has_group('student_management.group_student_accountant'):
            raise UserError(_('Only a student fees accountant can create fee invoices.'))
        if not self.env.user.has_group('account.group_account_invoice'):
            raise UserError(_('An Odoo Accounting invoicing role is required to create fee invoices.'))
        for fee in self:
            if fee.invoice_id:
                raise UserError(_('An invoice already exists for this fee.'))
            if not fee.partner_id:
                raise UserError(_('Select a student or guardian contact before invoicing.'))
            if fee.amount_total <= 0:
                raise UserError(_('The amount due must be greater than zero.'))
            company = fee.company_id
            journal = self.env['account.journal'].search([
                ('type', '=', 'sale'), ('company_id', '=', company.id),
            ], limit=1)
            if not journal:
                raise UserError(_('Configure a sales journal for the fee structure company first.'))
            structure = fee.fee_structure_id
            move = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': fee.partner_id.id,
                'company_id': company.id,
                'journal_id': journal.id,
                'invoice_date': fields.Date.context_today(self),
                'invoice_date_due': fee.due_date,
                'invoice_origin': fee.name,
                'invoice_line_ids': [Command.create({
                    'name': structure.name,
                    'quantity': 1,
                    'price_unit': fee.amount_total,
                    'account_id': structure.account_id.id,
                    'tax_ids': [Command.set(structure.tax_ids.ids)],
                })],
            })
            move.action_post()
            super(StudentFee, fee).write({'invoice_id': move.id})
        return self.action_view_invoice()

    def action_view_invoice(self):
        if not self.env.user.has_group('student_management.group_student_accountant'):
            raise UserError(_('Only a student fees accountant can open fee invoices.'))
        if not (
            self.env.user.has_group('account.group_account_invoice')
            or self.env.user.has_group('account.group_account_readonly')
        ):
            raise UserError(_('An Odoo Accounting role is required to open fee invoices.'))
        self.ensure_one()
        if not self.invoice_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Invoice'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
            'target': 'current',
        }

    def write(self, vals):
        if 'invoice_id' in vals:
            raise UserError(_('Link fee invoices through the student fee invoicing workflow.'))
        fee_fields = {
            'student_id', 'fee_structure_id', 'academic_year_id', 'period',
            'partner_id', 'due_date', 'amount', 'discount_amount',
        }
        if fee_fields.intersection(vals) and any(fee.invoice_id for fee in self):
            raise UserError(_('An invoiced fee cannot be changed. Create a new fee record for corrections.'))
        return super().write(vals)

    def unlink(self):
        if any(fee.invoice_id for fee in self):
            raise UserError(_('A fee linked to an invoice cannot be deleted.'))
        return super().unlink()

    @api.model
    def _cron_send_overdue_reminders(self):
        params = self.env['ir.config_parameter'].sudo()
        if not params.get_param('student_management.fee_reminders_enabled', 'True') == 'True':
            return
        try:
            repeat_days = max(1, int(params.get_param(
                'student_management.reminder_repeat_days', '7'
            )))
        except (TypeError, ValueError):
            repeat_days = 7
        today = fields.Date.context_today(self)
        cutoff = fields.Date.subtract(today, days=repeat_days)
        fees = self.search([
            ('due_date', '<', today), ('invoice_id.state', '=', 'posted'),
            ('balance_due', '>', 0),
            '|', ('reminder_last_sent', '=', False), ('reminder_last_sent', '<=', cutoff),
        ])
        template = self.env.ref(
            'student_management.mail_template_overdue_fee_reminder',
            raise_if_not_found=False,
        )
        if not template:
            return
        for fee in fees:
            if not fee.partner_id.email:
                continue
            template.send_mail(fee.id, force_send=False)
            fee.reminder_last_sent = today
