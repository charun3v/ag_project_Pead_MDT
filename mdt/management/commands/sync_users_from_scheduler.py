import os
import sqlite3
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from mdt.models import UserProfile, AuditLog


class Command(BaseCommand):
    help = "Imports users, roles, and exact password hashes from the Scheduler database"

    def add_arguments(self, parser):
        parser.add_argument(
            '--scheduler_db',
            type=str,
            default=r"D:\n3v\My projects\Databases\Scheduler\AG project - Scheduler\db.sqlite3",
            help="Path to Scheduler SQLite DB"
        )

    def handle(self, *args, **options):
        sch_path = options['scheduler_db']
        self.stdout.write(f"Connecting to Scheduler database: {sch_path}")

        if not os.path.exists(sch_path):
            self.stderr.write(f"Scheduler DB not found: {sch_path}")
            return

        conn = sqlite3.connect(sch_path)
        cursor = conn.cursor()

        # Map role_id to role_name
        cursor.execute("SELECT role_id, role_name FROM core_role")
        roles_map = dict(cursor.fetchall())
        self.stdout.write(f"Found roles in Scheduler: {roles_map}")

        cursor.execute("""
            SELECT u.id, u.username, u.password, u.first_name, u.last_name, u.email,
                   u.is_staff, u.is_superuser, u.is_active,
                   p.user_level, p.role_id, p.prefix
            FROM auth_user u
            LEFT JOIN core_userprofile p ON u.id = p.user_id
            ORDER BY u.id
        """)
        rows = cursor.fetchall()
        conn.close()

        count_created = 0
        count_updated = 0

        with transaction.atomic():
            for r in rows:
                uid, uname, pword_hash, fname, lname, email, is_staff, is_super, is_active, ulevel, role_id, prefix = r
                
                role_name = roles_map.get(role_id, 'Consultant')
                if uname in ['admin', 'n3v']:
                    role_name = 'Admin'
                    is_super = True
                    is_staff = True
                elif role_name == 'SubAdmin':
                    is_staff = True

                # Determine full name
                pfx = prefix.strip() if prefix else ""
                clean_fname = fname.strip() if fname else ""
                clean_lname = lname.strip() if lname else ""
                name_parts = [p for p in [pfx, clean_fname, clean_lname] if p]
                full_name_str = " ".join(name_parts) if name_parts else uname.capitalize()

                user, created = User.objects.get_or_create(username=uname)
                user.password = pword_hash
                user.first_name = clean_fname
                user.last_name = clean_lname
                user.email = email or ""
                user.is_staff = bool(is_staff)
                user.is_superuser = bool(is_super)
                user.is_active = bool(is_active)
                user.save()

                UserProfile.objects.update_or_create(
                    user=user,
                    defaults={
                        'role': role_name,
                        'user_level': ulevel or role_name.upper(),
                        'prefix': pfx or ('Dr.' if role_name in ['Consultant', 'Resident'] else ''),
                        'full_name': full_name_str,
                    }
                )

                if created:
                    count_created += 1
                else:
                    count_updated += 1

            # Log audit
            AuditLog.objects.create(
                username='System',
                full_name='System Migration',
                action='SYNC_SCHEDULER_USERS',
                table_affected='auth_user',
                record_ref=f'{len(rows)} users',
                notes=f'Synced {count_created} new users and updated {count_updated} existing users with Scheduler passwords and roles.'
            )

        self.stdout.write(self.style.SUCCESS(
            f"Successfully synced {len(rows)} users from Scheduler! ({count_created} created, {count_updated} updated)"
        ))
