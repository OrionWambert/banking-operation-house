-- Source table of the CDC pipeline: PeerDB replicates it to ClickHouse through logical replication,
-- so the primary key is required (it is the replica identity and the ClickHouse sorting key).

CREATE SEQUENCE banking_operation_seq START WITH 1 INCREMENT BY 50;

CREATE TABLE banking_operation
(
    id             bigint       NOT NULL PRIMARY KEY,
    amount         bigint       NOT NULL,
    client_name    varchar(255) NOT NULL,
    operation_date timestamp(6) NOT NULL,
    operation_type varchar(16)  NOT NULL CHECK (operation_type IN ('DEBIT', 'CREDIT'))
);
