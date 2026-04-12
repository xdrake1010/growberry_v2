import sqlite3
import os
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path='growberry.db'):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sensor TEXT NOT NULL,
                    value REAL NOT NULL
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_sensor_time ON measurements(sensor, timestamp)')
            conn.commit()

    def save_measurement(self, sensor: str, value: float):
        try:
            with self._get_connection() as conn:
                conn.execute(
                    'INSERT INTO measurements (timestamp, sensor, value) VALUES (?, ?, ?)',
                    (datetime.now().isoformat(), sensor, value)
                )
                conn.commit()
        except Exception as e:
            print(f"Error saving to DB: {e}")

    def get_history(self, sensor: str, limit: int = 100):
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    'SELECT timestamp, value FROM measurements WHERE sensor = ? ORDER BY timestamp DESC LIMIT ?',
                    (sensor, limit)
                )
                # Return in chronological order for charting
                return [{"timestamp": row[0], "value": row[1]} for row in cursor.fetchall()][::-1]
        except Exception as e:
            print(f"Error reading from DB: {e}")
            return []
