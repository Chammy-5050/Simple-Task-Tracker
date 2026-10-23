from django.db import migrations


# Include default-user tables if an older installation still contains them.
# Only known framework tables are moved; application tables stay in public.
FRAMEWORK_TABLES = (
    "django_content_type",
    "auth_permission",
    "auth_group",
    "auth_group_permissions",
    "auth_user",
    "auth_user_groups",
    "auth_user_user_permissions",
    "django_admin_log",
    "django_session",
    "django_migrations",
)


def move_tables(schema_editor, source, destination):
    if schema_editor.connection.vendor != "postgresql":
        raise RuntimeError("This schema migration requires PostgreSQL.")
    quote = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quote(destination)}")
        for table in FRAMEWORK_TABLES:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s)",
                [source, table],
            )
            if cursor.fetchone()[0]:
                # PostgreSQL preserves the data and moves associated indexes
                # and owned sequences; foreign keys retain their references.
                cursor.execute(
                    f"ALTER TABLE {quote(source)}.{quote(table)} "
                    f"SET SCHEMA {quote(destination)}"
                )


def forwards(apps, schema_editor):
    move_tables(schema_editor, "public", "django_internal")


def backwards(apps, schema_editor):
    move_tables(schema_editor, "django_internal", "public")
    # Leave the empty schema in place rather than drop unrelated objects.


class Migration(migrations.Migration):
    atomic = True
    dependencies = [
        ("STT", "0005_tasks_due_date"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("sessions", "0001_initial"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
