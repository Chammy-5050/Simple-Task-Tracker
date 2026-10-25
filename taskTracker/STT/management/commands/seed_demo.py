from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from STT.models import Projects, Tasks

# Every demo account uses this domain so the data can be found and removed safely.
DEMO_DOMAIN = "demo.tasktracker.test"
DEFAULT_PASSWORD = "Demo@2026!"

USERS = [
    # (local part, full name, phone, is admin)
    ("admin", "Kenneth P Mussa", "+255700000001", True),
    ("hubert", "Hubert Mrema", "+255700000002", False),
    ("sabrina", "Sabrina Kileo", "+255700000003", False),
    ("king", "King Sawa", "+255700000004", False),
]

# Due dates are day offsets from today so the calendar and reminders stay realistic.
PROJECTS = {
    "hubert": [
        ("JufMeester", "Learning platform for Dutch primary school teachers.", [
            ("Wireframe homepage", "Create a low-fidelity layout for the new landing page.", "done", -6),
            ("Registration page", "Build the registration page with validation states.", "in_progress", 0),
            ("Login page", "Implement sign in with remember-me and error handling.", "in_progress", 2),
            ("Email template QA", "Check rendering across major email clients.", "pending", -2),
            ("Design system audit", "Confirm spacing tokens match the Figma component library.", "pending", 9),
        ]),
        ("Barber Smart", "Booking and queue management for barbershops.", [
            ("Booking calendar", "Let customers pick a barber and a time slot.", "in_progress", 4),
            ("SMS reminders", "Send a reminder one hour before each booking.", "pending", 12),
            ("Payment integration", "Accept mobile money at checkout.", "pending", 20),
            ("Shop onboarding flow", None, "done", -10),
        ]),
    ],
    "sabrina": [
        ("School Education MP", "Education management platform for secondary schools.", [
            ("Checkout flow redesign", "Reduce drop-off by simplifying payment steps for invoices.", "in_progress", 1),
            ("Student report cards", "Generate printable term reports per class.", "pending", 6),
            ("Attendance dashboard", "Daily attendance summary for head teachers.", "done", -3),
            ("Parent portal access", "Invite parents with one-time links.", "pending", -1),
        ]),
    ],
    "king": [
        ("Agriculture Information", "Connecting farmers to market prices and extension advice.", [
            ("Market price feed", "Import daily crop prices from regional markets.", "in_progress", 3),
            ("Offline sync", "Queue farmer submissions while offline.", "pending", 15),
            ("Extension officer map", None, "pending", 25),
            ("Weather alerts", "Notify farmers of heavy rain forecasts.", "done", -5),
            ("Swahili translations", "Translate the mobile app into Swahili.", "in_progress", -4),
        ]),
    ],
}


class Command(BaseCommand):
    help = (
        f"Create or refresh demo accounts (@{DEMO_DOMAIN}), projects and tasks. "
        "Only records owned by demo accounts are touched."
    )

    def add_arguments(self, parser):
        parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password for every demo account.")
        parser.add_argument("--remove", action="store_true", help="Delete the demo accounts and their work instead.")

    @transaction.atomic
    def handle(self, *args, password, remove, **options):
        User = get_user_model()
        demo_users = User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}")
        if remove:
            Tasks.objects.filter(project_id__user_id__in=demo_users).delete()
            Projects.objects.filter(user_id__in=demo_users).delete()
            count = demo_users.count()
            demo_users.delete()
            self.stdout.write(self.style.SUCCESS(f"Removed {count} demo accounts and their work."))
            return

        today = timezone.localdate()
        accounts = {}
        for local, full_name, phone, is_admin in USERS:
            account, _ = User.objects.get_or_create(
                email=f"{local}@{DEMO_DOMAIN}",
                defaults={"full_name": full_name, "phone_no": phone},
            )
            account.full_name = full_name
            account.phone_no = phone
            account.is_active = True
            account.email_verified = True
            account.is_superuser = is_admin
            account.is_staff = is_admin
            account.set_password(password)
            account.save()
            accounts[local] = account

        task_count = 0
        for owner, projects in PROJECTS.items():
            for name, description, tasks in projects:
                project, _ = Projects.objects.update_or_create(
                    user_id=accounts[owner], project_name=name,
                    defaults={"description": description},
                )
                for task_name, task_description, status, offset in tasks:
                    Tasks.objects.update_or_create(
                        project_id=project, task_name=task_name,
                        defaults={
                            "description": task_description,
                            "status": status,
                            "due_date": today + timedelta(days=offset),
                        },
                    )
                    task_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(accounts)} accounts, {sum(len(p) for p in PROJECTS.values())} projects and {task_count} tasks."
        ))
        for local, full_name, _, is_admin in USERS:
            role = "admin " if is_admin else "member"
            self.stdout.write(f"  {role}  {local}@{DEMO_DOMAIN}  ({full_name})")
        self.stdout.write(f"  password: {password}")
