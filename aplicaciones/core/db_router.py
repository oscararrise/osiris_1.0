class ClientDatabaseRouter:
    """Keep Django-owned migrations out of external client databases."""

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db != "default":
            return False
        return None
