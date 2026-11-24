"""Provision Metabase for the banking dashboards. Standard library only; safe to run again.

Creates the admin account on a fresh Metabase (or logs in to an existing one), connects
ClickHouse, removes the demo content, renames the data model in French, and builds the
"Opérations bancaires" dashboard with its filters.

Run after the CDC mirror has created the ClickHouse table (scripts/setup-cdc.sh):

    MB_ADMIN_EMAIL=you@example.com MB_ADMIN_PASSWORD='...' python metabase/provision.py
"""

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

URL = os.environ.get("MB_URL", f"http://127.0.0.1:{os.environ.get('METABASE_PORT', '3002')}")
EMAIL = os.environ.get("MB_ADMIN_EMAIL")
PASSWORD = os.environ.get("MB_ADMIN_PASSWORD")

DATABASE_NAME = "Banque"
TABLE = "public_banking_operation"  # created by the PeerDB mirror
COLLECTION_NAME = "Banque"
DASHBOARD_NAME = "Opérations bancaires"

_session = None


def call(method: str, path: str, body: Any = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if _session:
        headers["X-Metabase-Session"] = _session
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(URL + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} failed ({e.code}): {e.read().decode()[:500]}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:  # some settings come back as plain text
        return raw.decode()


def log(message):
    print(f"- {message}", flush=True)


# ---------------------------------------------------------------------------------------- account

def login():
    global _session
    if not EMAIL or not PASSWORD:
        sys.exit("Set MB_ADMIN_EMAIL and MB_ADMIN_PASSWORD")
    properties = call("GET", "/api/session/properties")
    if not properties.get("has-user-setup"):
        _session = call("POST", "/api/setup", {
            "token": properties["setup-token"],
            "user": {"first_name": "Banking", "last_name": "Admin", "email": EMAIL,
                     "password": PASSWORD, "password_confirm": PASSWORD},
            "prefs": {"site_name": "Banking Operation House", "site_locale": "fr", "allow_tracking": False},
        })["id"]
        log(f"admin account created: {EMAIL}")
    else:
        _session = call("POST", "/api/session", {"username": EMAIL, "password": PASSWORD})["id"]
        log(f"logged in as {EMAIL}")


# ---------------------------------------------------------------------------------------- data

def clean_demo_content():
    for dashboard in call("GET", "/api/dashboard/"):
        if dashboard["name"] == "E-commerce Insights":
            call("PUT", f"/api/dashboard/{dashboard['id']}", {"archived": True})
            call("DELETE", f"/api/dashboard/{dashboard['id']}")
    for collection in call("GET", "/api/collection"):
        if collection["name"] == "Examples" and isinstance(collection["id"], int) and not collection.get("archived"):
            call("PUT", f"/api/collection/{collection['id']}", {"archived": True})
    for database in call("GET", "/api/database")["data"]:
        if database.get("is_sample"):
            call("DELETE", f"/api/database/{database['id']}")
    for key, value in {"site-name": "Banking Operation House", "site-locale": "fr", "start-of-week": "monday",
                       "show-homepage-xrays": False, "show-homepage-data": False, "enable-xrays": False}.items():
        call("PUT", f"/api/setting/{key}", {"value": value})
    log("demo content removed, settings applied")


def clickhouse_database():
    existing = [d for d in call("GET", "/api/database")["data"] if d["engine"] == "clickhouse"]
    if existing:
        database = existing[0]
        call("PUT", f"/api/database/{database['id']}", {"name": DATABASE_NAME})
    else:
        database = call("POST", "/api/database", {
            "engine": "clickhouse", "name": DATABASE_NAME,
            # Metabase runs in Docker: ClickHouse is reached by service name on its internal HTTP port
            "details": {"host": "clickhouse", "port": 8123, "dbname": "banking",
                        "user": "banking", "password": "banking", "ssl": False},
        })
        log("ClickHouse connected")
    return database["id"]


def wait_for_table(database_id):
    for attempt in range(60):
        tables = call("GET", f"/api/database/{database_id}/metadata?include_hidden=true")["tables"]
        table = next((t for t in tables if t["name"] == TABLE), None)
        if table:
            return table, tables
        if attempt % 10 == 0:
            call("POST", f"/api/database/{database_id}/sync_schema")
        time.sleep(3)
    sys.exit(f"Table {TABLE} not found in ClickHouse: run scripts/setup-cdc.sh and wait for the initial copy")


def describe_data_model(table, tables):
    for other in tables:
        if other["id"] != table["id"]:
            call("PUT", f"/api/table/{other['id']}", {"visibility_type": "hidden"})  # PeerDB staging tables
    call("PUT", f"/api/table/{table['id']}", {"display_name": "Opérations bancaires",
                                             "description": "Opérations répliquées depuis Postgres par PeerDB (CDC)."})
    # Fields hidden on a previous run are left out of the default metadata, so ask for them explicitly
    metadata = call("GET", f"/api/table/{table['id']}/query_metadata?include_sensitive_fields=true&include_hidden_fields=true")
    fields = {f["name"]: f["id"] for f in metadata["fields"]}
    for name, body in {
        "id": {"display_name": "Identifiant", "semantic_type": "type/PK"},
        "amount": {"display_name": "Montant", "semantic_type": "type/Currency",
                   "settings": {"currency": "XAF", "number_style": "currency"}},
        "client_name": {"display_name": "Client", "semantic_type": "type/Name"},
        "operation_date": {"display_name": "Date d'opération", "semantic_type": "type/CreationTimestamp"},
        "operation_type": {"display_name": "Type d'opération", "semantic_type": "type/Category"},
        "_peerdb_synced_at": {"display_name": "Synchronisé le", "visibility_type": "details-only"},
        "_peerdb_is_deleted": {"display_name": "Supprimé (CDC)", "visibility_type": "sensitive"},
        "_peerdb_version": {"display_name": "Version (CDC)", "visibility_type": "sensitive"},
    }.items():
        call("PUT", f"/api/field/{fields[name]}", body)
    log("data model described")
    return fields


# ---------------------------------------------------------------------------------------- dashboard

# FINAL collapses the row versions PeerDB writes on each change; deleted rows are flagged, not removed
SRC = f"banking.{TABLE} FINAL"
WHERE = "WHERE _peerdb_is_deleted = 0 [[AND {{periode}}]] [[AND {{type}}]] [[AND {{client}}]]"
TYPE_FR = "if(operation_type = 'CREDIT', 'Crédit', 'Débit')"
NET = "sumIf(amount, operation_type = 'CREDIT') - sumIf(amount, operation_type = 'DEBIT')"
RAW = f"banking.{TABLE}"


def money(*columns):
    return {"column_settings": {f'["name","{c}"]': {"number_style": "currency", "currency": "XAF",
                                                     "currency_style": "symbol"} for c in columns}}


def chart(dimensions, metrics, **extra):
    return {"graph.dimensions": dimensions, "graph.metrics": metrics, **extra}


# name, SQL, display, visualization settings, filterable, (col, row, width, height) on a 24-column grid
CARDS = [
    ("Nombre d'opérations", f"SELECT count() AS `Opérations` FROM {SRC} {WHERE}",
     "scalar", {}, True, (0, 0, 6, 3)),
    ("Volume total", f"SELECT sum(amount) AS `Volume` FROM {SRC} {WHERE}",
     "scalar", money("Volume"), True, (6, 0, 6, 3)),
    ("Solde net (crédits − débits)", f"SELECT {NET} AS `Solde net` FROM {SRC} {WHERE}",
     "scalar", money("Solde net"), True, (12, 0, 6, 3)),
    ("Clients actifs", f"SELECT uniqExact(client_name) AS `Clients` FROM {SRC} {WHERE}",
     "scalar", {}, True, (18, 0, 6, 3)),
    ("Opérations par jour",
     f"SELECT toDate(operation_date) AS `Jour`, {TYPE_FR} AS `Type`, count() AS `Opérations` "
     f"FROM {SRC} {WHERE} GROUP BY `Jour`, `Type` ORDER BY `Jour`",
     "line", chart(["Jour", "Type"], ["Opérations"]), True, (0, 3, 16, 6)),
    ("Répartition crédits / débits",
     f"SELECT {TYPE_FR} AS `Type`, count() AS `Opérations` FROM {SRC} {WHERE} GROUP BY `Type`",
     "pie", {"pie.dimension": "Type", "pie.metric": "Opérations"}, True, (16, 3, 8, 6)),
    ("Volume mensuel par type",
     f"SELECT toStartOfMonth(operation_date) AS `Mois`, {TYPE_FR} AS `Type`, sum(amount) AS `Volume` "
     f"FROM {SRC} {WHERE} GROUP BY `Mois`, `Type` ORDER BY `Mois`",
     "bar", {**chart(["Mois", "Type"], ["Volume"], **{"stackable.stack_type": "stacked"}), **money("Volume")},
     True, (0, 9, 12, 6)),
    ("Solde net mensuel",
     f"SELECT toStartOfMonth(operation_date) AS `Mois`, {NET} AS `Solde net` "
     f"FROM {SRC} {WHERE} GROUP BY `Mois` ORDER BY `Mois`",
     "bar", {**chart(["Mois"], ["Solde net"]), **money("Solde net")}, True, (12, 9, 12, 6)),
    ("Top 10 clients par volume",
     f"SELECT client_name AS `Client`, count() AS `Opérations`, sum(amount) AS `Volume`, {NET} AS `Solde net` "
     f"FROM {SRC} {WHERE} GROUP BY `Client` ORDER BY `Volume` DESC LIMIT 10",
     "row", {**chart(["Client"], ["Volume"]), **money("Volume", "Solde net")}, True, (0, 15, 12, 7)),
    ("Répartition des montants",
     "SELECT multiIf(amount < 1000, '1. moins de 1 000', amount < 10000, '2. 1 000 – 10 000', "
     "amount < 100000, '3. 10 000 – 100 000', amount < 500000, '4. 100 000 – 500 000', '5. 500 000 et plus') "
     f"AS `Tranche (FCFA)`, count() AS `Opérations` FROM {SRC} {WHERE} "
     "GROUP BY `Tranche (FCFA)` ORDER BY `Tranche (FCFA)`",
     "bar", chart(["Tranche (FCFA)"], ["Opérations"]), True, (12, 15, 12, 7)),
    ("Activité par heure",
     f"SELECT toHour(operation_date) AS `Heure`, count() AS `Opérations` FROM {SRC} {WHERE} "
     "GROUP BY `Heure` ORDER BY `Heure`",
     "bar", chart(["Heure"], ["Opérations"]), True, (0, 22, 12, 7)),
    ("Dernières opérations",
     f"SELECT id AS `N° opération`, operation_date AS `Date`, client_name AS `Client`, {TYPE_FR} AS `Type`, "
     f"amount AS `Montant` FROM {SRC} {WHERE} ORDER BY `N° opération` DESC LIMIT 50",
     "table", money("Montant"), True, (12, 22, 12, 7)),
    # CDC health: read the raw table, so they also show row versions not merged yet
    ("Dernière synchronisation", f"SELECT max(_peerdb_synced_at) AS `Dernière synchro` FROM {RAW}",
     "scalar", {}, False, (0, 30, 8, 3)),
    ("Lignes synchronisées (dernière heure)",
     f"SELECT count() AS `Lignes` FROM {RAW} WHERE _peerdb_synced_at > now() - INTERVAL 1 HOUR",
     "scalar", {}, False, (8, 30, 8, 3)),
    ("Versions en attente de fusion",
     f"SELECT (SELECT count() FROM {RAW}) - (SELECT count() FROM {SRC}) AS `Versions`",
     "scalar", {}, False, (16, 30, 8, 3)),
    ("Lignes synchronisées par minute",
     f"SELECT toStartOfMinute(_peerdb_synced_at) AS `Minute`, count() AS `Lignes` FROM {RAW} "
     "WHERE _peerdb_synced_at > now() - INTERVAL 1 DAY GROUP BY `Minute` ORDER BY `Minute`",
     "bar", chart(["Minute"], ["Lignes"]), False, (0, 33, 24, 6)),
]
CDC_HEADING = ("Santé de la réplication CDC (PeerDB → ClickHouse)", (0, 29, 24, 1))

PARAMETERS = [
    {"id": "periode", "name": "Période", "slug": "periode", "type": "date/all-options", "sectionId": "date"},
    {"id": "type", "name": "Type d'opération", "slug": "type", "type": "string/=", "sectionId": "string"},
    {"id": "client", "name": "Client", "slug": "client", "type": "string/=", "sectionId": "string"},
]


def template_tags(fields):
    def tag(name, label, field, widget):
        return {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"banking/{name}")), "name": name, "display-name": label,
                "type": "dimension", "dimension": ["field", fields[field], None], "widget-type": widget}
    return {"periode": tag("periode", "Période", "operation_date", "date/all-options"),
            "type": tag("type", "Type d'opération", "operation_type", "string/="),
            "client": tag("client", "Client", "client_name", "string/=")}


def collection_id():
    for collection in call("GET", "/api/collection"):
        if collection["name"] == COLLECTION_NAME and not collection.get("archived"):
            return collection["id"]
    return call("POST", "/api/collection", {"name": COLLECTION_NAME, "description": "Analyses des opérations bancaires"})["id"]


def build_dashboard(database_id, fields):
    collection = collection_id()
    dashboard = next((d for d in call("GET", "/api/dashboard/")
                      if d["name"] == DASHBOARD_NAME and d.get("collection_id") == collection), None)
    if dashboard is None:
        dashboard = call("POST", "/api/dashboard", {"name": DASHBOARD_NAME, "collection_id": collection})
    dashboard_id = dashboard["id"]
    current = call("GET", f"/api/dashboard/{dashboard_id}")
    existing_cards = {dc["card"]["name"]: dc["card_id"] for dc in current["dashcards"] if dc.get("card_id")}

    dashcards = []
    for index, (name, sql, display, viz, filterable, (col, row, width, height)) in enumerate(CARDS):
        card = {"name": name, "display": display, "visualization_settings": viz,
                "dataset_query": {"type": "native", "database": database_id,
                                  "native": {"query": sql, "template-tags": template_tags(fields) if filterable else {}}}}
        if name in existing_cards:
            card_id = existing_cards[name]
            call("PUT", f"/api/card/{card_id}", card)
        else:
            # Stored inside the dashboard, so the collection only lists the dashboard itself
            card_id = call("POST", "/api/card", {**card, "dashboard_id": dashboard_id})["id"]
        mappings = [{"parameter_id": p["id"], "card_id": card_id, "target": ["dimension", ["template-tag", p["id"]]]}
                    for p in PARAMETERS] if filterable else []
        dashcards.append({"id": -(index + 1), "card_id": card_id, "col": col, "row": row, "size_x": width,
                          "size_y": height, "parameter_mappings": mappings, "visualization_settings": {}})

    heading, (col, row, width, height) = CDC_HEADING
    dashcards.append({"id": -(len(CARDS) + 1), "card_id": None, "col": col, "row": row, "size_x": width,
                      "size_y": height, "parameter_mappings": [],
                      "visualization_settings": {"virtual_card": {"name": None, "display": "heading",
                                                                  "visualization_settings": {}, "dataset_query": {},
                                                                  "archived": False},
                                                 "text": heading}})

    call("PUT", f"/api/dashboard/{dashboard_id}", {
        "description": "Activité des opérations bancaires (répliquées de Postgres vers ClickHouse) et santé du CDC.",
        "parameters": PARAMETERS, "dashcards": dashcards, "collection_position": 1,
    })
    call("PUT", "/api/setting/custom-homepage", {"value": True})
    call("PUT", "/api/setting/custom-homepage-dashboard", {"value": dashboard_id})
    log(f"dashboard ready: {URL}/dashboard/{dashboard_id} ({len(CARDS)} cards)")
    return dashboard_id


def check(dashboard_id):
    """Runs every card once so a broken query fails the provisioning instead of the dashboard."""
    failures = 0
    for dc in call("GET", f"/api/dashboard/{dashboard_id}")["dashcards"]:
        if not dc.get("card_id"):
            continue
        result = call("POST", f"/api/dashboard/{dashboard_id}/dashcard/{dc['id']}/card/{dc['card_id']}/query",
                      {"parameters": []})
        if result.get("error"):
            failures += 1
            print(f"  ! {dc['card']['name']}: {result['error']}", flush=True)
    if failures:
        sys.exit(f"{failures} card(s) failed")
    log("every card returns data")


if __name__ == "__main__":
    if isinstance(sys.stdout, io.TextIOWrapper):  # Windows consoles default to a legacy code page
        sys.stdout.reconfigure(encoding="utf-8")
    login()
    clean_demo_content()
    database_id = clickhouse_database()
    table, tables = wait_for_table(database_id)
    fields = describe_data_model(table, tables)
    check(build_dashboard(database_id, fields))
