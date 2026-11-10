{
	'name': 'Student Management',
	'version':'19.0.11.0.0',
	'category': 'Education',
	'summary': 'Manage students and  their information',
	'description':"""
	    Student Managemaent System
	   ===========================
	   This module Manages student records.
	""",
	'author': 'Sanwal',
	'license': 'LGPL-3',
	'depends': ['base', 'web', 'mail', 'account'],
	'data': [
		        'security/student_security.xml',
		        'data/student_sequence.xml',
		        'security/ir.model.access.csv',
		'data/student_mail_template.xml',
		'data/student_cron.xml',
		'views/student_views.xml',
		'views/student_reporting_views.xml',
		'views/student_settings_views.xml',
		'reports/student_reports.xml',
	],
	'installable': True,
	'application': True,
}
