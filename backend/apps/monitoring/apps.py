from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.monitoring"
    verbose_name = "Monitoring"

    def ready(self):
        # Register the production-hardening Django system checks. Imported
        # lazily inside `ready()` so the app registry is guaranteed loaded.
        from . import checks  # noqa: PLC0415,F401