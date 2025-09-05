# Central place for database credentials.
# Later: move sensitive values to environment variables.
DB_CONFIG = {
    "dbname": "inventory_db",
    "user": "postgres",
    "password": "MANman1@6",   # TODO: pull from env (e.g. os.environ.get("INV_DB_PASS"))
    "host": "192.168.0.90",
    "port": "5432",
}