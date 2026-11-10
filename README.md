# Student Management for Odoo 19

An education management addon for schools, colleges, universities, and training institutes. It uses Odoo Contacts, Mail, and Accounting for student contacts, notifications, invoices, and payment state. Student and guardian portal access is outside the current scope.

## Features

- Student records with generated IDs, admission details, class and section placement, guardians, documents, and archive support.
- Academic years, classes, sections, courses, teacher assignments, and enrollment history.
- Attendance sessions with confirmation workflow and attendance percentages.
- Examinations, result entry, grade and pass/fail calculations, result cards, and confirmation locks.
- Fee structures and student fee records linked to Odoo customer invoices and payment status.
- Overview dashboard, graph and pivot analysis, scheduled reminders, and PDF reports.

## Requirements

- Odoo 19
- The Odoo addons `base`, `web`, `mail`, and `account` (declared as addon dependencies)
- For fee invoicing: a configured company, sales journal, income account, and an Accounting user with permission to create and post customer invoices
- For email notifications: a working outgoing mail server and valid recipient addresses

## Installation and upgrade

1. Place this directory in an Odoo addons path.
2. Start or restart Odoo, update the Apps list, and install **Student Management**.

   To install from the command line:

   ```sh
   ./odoo-bin --addons-path=/path/to/odoo/addons,/path/to/custom/addons -d DATABASE -i student_management --stop-after-init
   ```

   To upgrade an existing database:

   ```sh
   ./odoo-bin --addons-path=/path/to/odoo/addons,/path/to/custom/addons -d DATABASE -u student_management --stop-after-init
   ```

3. Assign staff to the appropriate Student Management group and configure company accounting and outgoing mail before using invoicing or email reminders.
4. In **Settings → General Settings → Student Management**, configure the attendance threshold, reminder interval, and notification switches. The scheduled reminder jobs run daily.

## User groups and access

- **Admission Staff** manage student and academic records, guardian links, documents, and student fees. Personal student contact and guardian details are restricted to this group (with the student partner link also available to fee accountants).
- **Student Management Administrator** inherits Admission Staff access and receives additional manager ACLs. Student deletion is blocked at the model level; archive students instead.
- **Teacher** access is limited to assigned academic records through record rules, ACLs, workflow locks, and server-side assignment checks. Teachers cannot send admission emails or access fee records.
- **Student Fees Accountant** can access student fee records and fee structures, with limited student, class, and academic-year reads. Access to Odoo invoices and posting actions also depends on the user's standard Odoo Accounting groups.

Access is enforced through ACLs, record rules, field groups, and model validation. Fee records and fee structures are additionally restricted to companies enabled for the current user. Menu visibility alone is not an access control. Validate the intended groups and workflows on the institution's Odoo database before production deployment.

## Notifications

- Low-attendance alerts are queued daily for active students below the configured attendance threshold, provided they have confirmed, marked attendance. Emails go to linked guardians with email addresses; the student email is used only when no guardian email is available.
- Overdue fee reminders are queued daily for posted invoices past their due date with a positive outstanding balance. The reminder interval suppresses repeat messages per student alert or fee record; it is not tracked separately for each recipient.
- Review the Odoo email queue and outgoing mail server configuration. Notification jobs do not send successfully without valid recipient addresses and a working mail setup.

## Dashboards and reports

The **Student Management → Overview** dashboard and **Reports** menu provide role-scoped indicators and attendance, examination, and fee analysis. Available PDF reports from record Print menus are:

- Student Profile (Admission Staff)
- Student Result Card (Admission Staff and Teachers)
- Student Fee Statement (Admission Staff and Student Fees Accountants)
- Attendance Register (Admission Staff and Teachers)
- Examination Results (Admission Staff and Teachers)

Teachers' report access is also subject to the model's record rules. The fee dashboard total is scoped to the active company. Check the assigned groups before printing documents containing student contact, academic, or financial information.

## Integrations

Fee invoicing creates Odoo customer invoices from fee records. Configure the appropriate company, sales journal, income account, taxes, and customer contact before issuing invoices. Payment status and residual amounts are read from Accounting. Do not create duplicate fee or invoice records outside the addon workflow without reconciling them with the linked fee record.

The addon does not define unauthenticated custom HTTP endpoints. For external integrations, use Odoo's authenticated API/RPC mechanisms with a dedicated user and the minimum required groups. Review ACLs, record rules, company access, and model validations for that user before connecting an external system.

## Tests

The repository includes transaction tests for student identity/contact synchronization, validation, age and archive behavior, attendance confirmation/calculation, examination enrollment/result locking, fee discount validation and invoice posting, teacher access boundaries, company restrictions, scheduled reminder cooldowns, and report registration. It does not render PDFs or connect to an outgoing mail server in tests, and the suite has not been run against Odoo in this workspace.

Run the addon tests against a disposable Odoo 19 test database when verification is requested:

```sh
./odoo-bin --addons-path=/path/to/odoo/addons,/path/to/custom/addons -d student_management_test -u student_management --test-enable --stop-after-init
```

## Backup and maintenance

- Back up PostgreSQL and the matching Odoo filestore together; uploaded student documents may be stored in the filestore.
- Test restoring backups to a separate database before applying upgrades or removing records.
- Apply addon upgrades in staging first. Review Odoo logs, cron status, email queue, invoice creation, and PDF rendering.
- Keep Odoo, PostgreSQL, the host operating system, and mail configuration maintained and monitored.
- Protect backups and production access according to the institution's student-data retention and privacy requirements.

## Project status

See [ROADMAP.md](ROADMAP.md) for the implementation phases and remaining work. Phase 4 features and the code-level role/company security review are complete; Odoo runtime installation and performance benchmarking remain.
