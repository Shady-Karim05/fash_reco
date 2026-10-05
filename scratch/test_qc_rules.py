"""Test script to evaluate quality control rules on data/catalog.db."""

import sqlite3
import re
import html
from collections import Counter

conn = sqlite3.connect('data/catalog.db')
cursor = conn.cursor()
cursor.execute('SELECT parent_asin, title, price, slot, store, description, features, average_rating, rating_number FROM products')
rows = cursor.fetchall()
print(f"Total products in catalog: {len(rows)}")

slots = Counter(r[3] for r in rows)
print("Initial slot breakdown:", slots)
