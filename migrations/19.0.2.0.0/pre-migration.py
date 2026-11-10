def migrate(cr, version):
    """Give existing records stable identifiers before required fields are added."""
    cr.execute("SELECT to_regclass('student_student')")
    if cr.fetchone()[0]:
        cr.execute("ALTER TABLE student_student ADD COLUMN IF NOT EXISTS student_number varchar")
        cr.execute("""
            UPDATE student_student
               SET student_number = 'STU-OLD-' || id
             WHERE student_number IS NULL OR student_number = ''
        """)
        cr.execute("ALTER TABLE student_student ADD COLUMN IF NOT EXISTS legacy_age integer")
        cr.execute("""
            UPDATE student_student
               SET legacy_age = age
             WHERE legacy_age IS NULL
        """)

    cr.execute("SELECT to_regclass('student_course')")
    if cr.fetchone()[0]:
        cr.execute("ALTER TABLE student_course ADD COLUMN IF NOT EXISTS code varchar")
        cr.execute("""
            UPDATE student_course
               SET code = 'CRS-OLD-' || id
             WHERE code IS NULL OR code = ''
        """)
