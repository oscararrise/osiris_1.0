"""The dashboard owns no sensor tables.

Every sensor database is accessed through an explicit read-only adapter instead of
unmanaged Django models, because each client may supply a different schema.
"""
