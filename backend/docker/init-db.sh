#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
CREATE ROLE grafana_ro LOGIN PASSWORD '${GRAFANA_DB_PASSWORD}';
GRANT USAGE ON SCHEMA public TO grafana_ro;
-- Las tablas las crea la API más tarde; este permiso se aplica a las que cree "$POSTGRES_USER".
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
SQL
