import os
import sqlite3
from typing import List, Dict, Any

SYNC_TABLE_NAME = "sync_records"
SYNC_TABLE_SCHEMA = """
id INTEGER PRIMARY KEY AUTOINCREMENT,
path TEXT NOT NULL,
size INTEGER NOT NULL,
mod_time FLOAT NOT NULL,
source_path TEXT DEFAULT NULL
"""


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """
    Establish a connection to the SQLite database.
    If the database file doesn't exist, it will be created.

    :param db_path: Path to the SQLite database file.
    :return: SQLite connection object.
    """
    # Ensure the directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    # SQLite will create the file if it doesn't exist
    return sqlite3.connect(db_path)


def create_table(db_path: str, table_name: str, schema: str) -> None:
    """
    Create a new table in the database with the specified schema.

    :param db_path: Path to the SQLite database file.
    :param table_name: Name of the table to create.
    :param schema: SQL schema definition for the table.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({schema})"

    try:
        cursor.execute(sql)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def fetch_records(db_path: str, query: str) -> List[Dict[str, Any]]:
    """
    Fetch records from the database based on the provided query.

    :param db_path: Path to the SQLite database file.
    :param query: SQL query to execute.
    :return: List of records as dictionaries.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        records = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return records
    finally:
        cursor.close()
        conn.close()


def insert_record(db_path: str, table: str, data: Dict[str, Any]) -> None:
    """
    Insert a record into the specified table in the database.

    :param db_path: Path to the SQLite database file.
    :param table: Name of the table to insert the record into.
    :param data: Dictionary containing column names and values to insert.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

    try:
        cursor.execute(sql, tuple(data.values()))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def batch_insert_records(
    db_path: str, table: str, records: List[Dict[str, Any]], batch_size: int = 1000
) -> None:
    """
    Insert multiple records into the specified table in the database in batches.

    :param db_path: Path to the SQLite database file.
    :param table: Name of the table to insert the records into.
    :param records: List of dictionaries containing column names and values to insert.
    :param batch_size: Number of records to insert in each batch.
    """

    if not records:
        return

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    columns = ", ".join(records[0].keys())
    placeholders = ", ".join(["?"] * len(records[0]))
    sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

    try:
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            cursor.executemany(sql, [tuple(record.values()) for record in batch])
            conn.commit()
    finally:
        cursor.close()
        conn.close()


def update_record(
    db_path: str, table: str, data: Dict[str, Any], where_column: str, where_value: Any
) -> None:
    """
    Update a record in the specified table in the database.

    :param db_path: Path to the SQLite database file.
    :param table: Name of the table to update the record in.
    :param data: Dictionary containing column names and values to update.
    :param where_column: Column name for the WHERE condition.
    :param where_value: Value for the WHERE condition.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    set_clause = ", ".join([f"{key} = ?" for key in data.keys()])
    sql = f"UPDATE {table} SET {set_clause} WHERE {where_column} = ?"

    # Create parameter list with all values plus the where value
    params = list(data.values()) + [where_value]

    try:
        cursor.execute(sql, params)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def delete_record(
    db_path: str, table: str, where_column: str, where_value: Any
) -> None:
    """
    Delete a record from the specified table in the database.

    :param db_path: Path to the SQLite database file.
    :param table: Name of the table to delete the record from.
    :param where_column: Column name for the WHERE condition.
    :param where_value: Value for the WHERE condition.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    sql = f"DELETE FROM {table} WHERE {where_column} = ?"

    try:
        cursor.execute(sql, (where_value,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def make_sync_table(db_path: str) -> None:
    """
    Create the sync records table in the database.

    :param db_path: Path to the SQLite database file.
    """
    create_table(db_path, SYNC_TABLE_NAME, SYNC_TABLE_SCHEMA)


def get_sync_table(db_path: str) -> List[Dict[str, Any]]:
    """
    Fetch all records from the sync records table.

    :param db_path: Path to the SQLite database file.
    :return: List of sync records as dictionaries.
    """
    query = f"SELECT * FROM {SYNC_TABLE_NAME}"
    return fetch_records(db_path, query)
