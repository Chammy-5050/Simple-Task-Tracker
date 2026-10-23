from django.db import migrations


def align_admin_log_user(apps, schema_editor):
    """Repair the empty legacy admin log created before AUTH_USER_MODEL changed."""
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'django_admin_log' AND column_name = 'user_id'"
        )
        column = cursor.fetchone()
        if column is None or column[0] == "uuid":
            return

        cursor.execute("SELECT COUNT(*) FROM django_admin_log")
        if cursor.fetchone()[0]:
            raise RuntimeError(
                "Legacy admin log has entries. Map its old user IDs to UUID users "
                "before changing its foreign key; no log entries were deleted."
            )

        constraints = connection.introspection.get_constraints(cursor, "django_admin_log")
        quote = schema_editor.quote_name
        for name, constraint in constraints.items():
            if constraint.get("foreign_key") and constraint["columns"] == ["user_id"]:
                cursor.execute(
                    f"ALTER TABLE django_admin_log DROP CONSTRAINT {quote(name)}"
                )
        cursor.execute(
            "ALTER TABLE django_admin_log ALTER COLUMN user_id TYPE uuid USING NULL::uuid"
        )
        User = apps.get_model("STT", "Users")
        cursor.execute(
            "ALTER TABLE django_admin_log "
            "ADD CONSTRAINT stt_admin_log_user_fk FOREIGN KEY (user_id) "
            f"REFERENCES {quote(User._meta.db_table)} ({quote(User._meta.pk.column)}) "
            "DEFERRABLE INITIALLY DEFERRED"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("STT", "0002_users_is_staff"),
        ("admin", "0003_logentry_add_action_flag_choices"),
    ]

    operations = [
        migrations.RunPython(align_admin_log_user, migrations.RunPython.noop),
    ]
