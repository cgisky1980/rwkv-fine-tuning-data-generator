import sqlite3
conn = sqlite3.connect('data/tasks.db')
conn.execute('ALTER TABLE tasks ADD COLUMN generator_type TEXT NOT NULL DEFAULT "unknown"')
conn.commit()
print('Added column')
conn.close()
