#!/usr/bin/env bash
# Creates the PeerDB peers and the Postgres -> ClickHouse CDC mirror. Safe to run again.
# Requires the stack to be up: docker compose --profile cdc up -d --wait
set -euo pipefail
cd "$(dirname "$0")/.."

# peerdb-server speaks the Postgres wire protocol; psql runs from the postgres container,
# which is on the same Docker network, so the peers use service names, not localhost.
peerdb() {
    docker compose exec -T postgres \
        psql "host=peerdb-server port=9900 user=peerdb password=peerdb dbname=peerdb" -v ON_ERROR_STOP=1 -q "$@"
}

peerdb <<'SQL'
CREATE PEER IF NOT EXISTS banking_postgres FROM POSTGRES WITH (
    host = 'postgres', port = 5432, user = 'banking', password = 'banking', database = 'banking'
);

CREATE PEER IF NOT EXISTS banking_clickhouse FROM CLICKHOUSE WITH (
    host = 'clickhouse', port = 9000, user = 'banking', password = 'banking', database = 'banking',
    disable_tls = true
);

CREATE MIRROR IF NOT EXISTS banking_cdc FROM banking_postgres TO banking_clickhouse
WITH TABLE MAPPING (public.banking_operation:public_banking_operation)
WITH (do_initial_copy = true, sync_interval = 10);
SQL

echo "CDC mirror 'banking_cdc' ready: http://localhost:${PEERDB_UI_PORT:-3001}/mirrors/banking_cdc"
