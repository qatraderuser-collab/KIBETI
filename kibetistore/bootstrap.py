"""Bring the production database up to date on serverless cold start.

Vercel's Python runtime has no release phase and its sensitive database credentials are only
available inside the deployment, so migrations and the initial catalog seed run here. A Postgres
advisory lock on a direct (non-pooled) connection ensures concurrent cold starts do this once.
"""

import logging
import os

logger = logging.getLogger(__name__)

_LOCK_KEY = 7_514_221_001


def _direct_lock_connection():
    url = os.environ.get("POSTGRES_URL_NON_POOLING")
    if not url:
        return None
    import psycopg

    return psycopg.connect(url, autocommit=True, connect_timeout=10)


def _pending_migrations():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    return executor.migration_plan(executor.loader.graph.leaf_nodes())


def _catalog_is_empty():
    from store.models import Product

    return not Product.objects.exists()


def ensure_admin():
    """Create or refresh the site admin from DJANGO_ADMIN_USERNAME / DJANGO_ADMIN_PASSWORD.

    The credentials live only in the deployment's environment variables, never in the repo.
    """
    username = os.environ.get("DJANGO_ADMIN_USERNAME")
    password = os.environ.get("DJANGO_ADMIN_PASSWORD")
    if not username or not password:
        return
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user, created = User.objects.get_or_create(username=username)
    if created or not user.check_password(password) or not (user.is_staff and user.is_superuser):
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        logger.warning("Admin user %s %s", username, "created" if created else "updated")


def ensure_database_ready():
    from django.conf import settings
    from django.core.management import call_command

    if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        return

    try:
        if not _pending_migrations() and not _catalog_is_empty():
            ensure_admin()
            return
    except Exception:
        pass  # Tables may not exist yet; fall through to the locked path.

    lock_conn = _direct_lock_connection()
    try:
        if lock_conn is not None:
            lock_conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))

        if _pending_migrations():
            logger.warning("Applying pending migrations on cold start")
            call_command("migrate", interactive=False, verbosity=0)

        if _catalog_is_empty():
            logger.warning("Seeding catalog fixture on cold start")
            call_command("loaddata", "catalog", verbosity=0)

        ensure_admin()
    finally:
        if lock_conn is not None:
            try:
                lock_conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
            finally:
                lock_conn.close()
