import sqlite3

conn = sqlite3.connect('data/catalog.db')
cursor = conn.cursor()
cursor.execute('SELECT parent_asin, title, price, slot FROM products WHERE slot = "unknown" LIMIT 20')
for row in cursor.fetchall():
    print(row)
