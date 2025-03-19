import psycopg2

DATABASE_URL = "postgresql://robot_user:140504@localhost/robot_db"

try:
    # Kết nối tới database
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Kiểm tra danh sách bảng
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
    tables = cur.fetchall()

    print("✅ Kết nối thành công! Danh sách bảng:")
    for table in tables:
        print("-", table[0])

    # Đóng kết nối
    cur.close()
    conn.close()
except Exception as e:
    print("❌ Lỗi kết nối:", e)
