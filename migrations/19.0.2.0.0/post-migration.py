def migrate(cr, version):
    """Move legacy direct course links into the enrollment history model."""
    cr.execute("SELECT to_regclass('student_course_rel'), to_regclass('student_enrollment')")
    legacy_table, enrollment_table = cr.fetchone()
    if not legacy_table or not enrollment_table:
        return

    cr.execute("""
        INSERT INTO student_enrollment
            (student_id, course_id, enrollment_date, state,
             create_uid, create_date, write_uid, write_date)
        SELECT relation.student_id, relation.course_id,
               COALESCE(student.enrollment_date, student.create_date::date, CURRENT_DATE),
               'enrolled',
               1, NOW(), 1, NOW()
          FROM student_course_rel relation
          JOIN student_student student ON student.id = relation.student_id
         WHERE NOT EXISTS (
               SELECT 1
                 FROM student_enrollment enrollment
                WHERE enrollment.student_id = relation.student_id
                  AND enrollment.course_id = relation.course_id
                  AND enrollment.academic_year_id IS NULL
         )
    """)
