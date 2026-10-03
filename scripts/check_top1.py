import sqlite3

conn = sqlite3.connect("data/catalog.db")
cur = conn.cursor()
row = cur.execute(
    "SELECT parent_asin, title, average_rating, rating_number, quality_score "
    "FROM products WHERE title LIKE 'Summer Floral Bikini Swimwear Cover Up Wrap M%'"
).fetchone()
print("Product row:", row)

cur.execute("SELECT MIN(quality_score), MAX(quality_score) FROM products WHERE is_deleted=0")
bounds = cur.fetchone()
print("Bounds (min, max):", bounds)

if row and bounds:
    q_norm = (row[4] - bounds[0]) / (bounds[1] - bounds[0])
    print("q_norm:", q_norm)
    print("quality boost (weight=0.05):", 0.05 * q_norm)
