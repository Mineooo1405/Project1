from sqlalchemy import create_engine, text

# Cấu hình kết nối PostgreSQL (sửa lại nếu cần)
DATABASE_URL = "postgresql://robot_user:140504@localhost/robot_db"

# Kết nối đến database
engine = create_engine(DATABASE_URL)

def fetch_data():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM imu_logs ORDER BY timestamp DESC LIMIT 10"))
        for row in result:
            print(row)

fetch_data()
