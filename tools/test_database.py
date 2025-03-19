import sys
import os
import datetime
import traceback

# Add parent directory to path to import database modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from sqlalchemy import text
    from back.database import SessionLocal, IMUData, Base, engine, DATABASE_URL
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

def test_db_connection():
    """Test database connection and create tables if needed"""
    print("Testing database connection...")
    print(f"Using database URL: {DATABASE_URL}")
    
    try:
        # Create a session
        db = SessionLocal()
        
        # Try a simple query - using text() to explicitly mark as SQL
        result = db.execute(text("SELECT 1")).scalar()
        
        if result == 1:
            print("✅ Database connection successful!")
        
        # Check if IMUData table exists
        print("Checking for required tables...")
        try:
            tables_result = db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")).fetchall()
            tables = [row[0] for row in tables_result]
            print(f"Existing tables: {', '.join(tables)}")
        except:
            print("Could not query existing tables")
        
        # Create all tables if they don't exist
        print("Creating/updating tables...")
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created/updated successfully!")
        
        # Insert a test IMU record
        test_record = IMUData(
            robot_id="test_robot",
            accel_x=1.0,
            accel_y=2.0, 
            accel_z=9.8,
            gyro_x=0.1,
            gyro_y=0.2,
            gyro_z=0.3,
            timestamp=datetime.datetime.now(),
            raw_data={"test": True}
        )
        
        db.add(test_record)
        db.commit()
        
        print(f"✅ Test IMU record inserted with id: {test_record.id}")
        
        # Retrieve and verify the record
        retrieved = db.query(IMUData).filter(IMUData.id == test_record.id).first()
        if retrieved:
            print(f"✅ Retrieved test record: robot_id={retrieved.robot_id}, accel_z={retrieved.accel_z}")
        else:
            print("❌ Failed to retrieve test record")
        
    except Exception as e:
        print(f"❌ Database error: {str(e)}")
        print("Stack trace:")
        traceback.print_exc()
    finally:
        if 'db' in locals():
            db.close()
        print("Connection closed")

def check_postgresql():
    """Additional check for PostgreSQL connection"""
    try:
        import psycopg2
        print("\nTesting direct PostgreSQL connection...")
        
        # Extract connection parameters from DATABASE_URL
        # Format: postgresql://username:password@host:port/dbname
        conn_parts = DATABASE_URL.replace("postgresql://", "").split("@")
        user_pass = conn_parts[0].split(":")
        username = user_pass[0]
        password = user_pass[1] if len(user_pass) > 1 else ""
        
        host_port_db = conn_parts[1].split("/")
        host_port = host_port_db[0].split(":")
        host = host_port[0]
        port = host_port[1] if len(host_port) > 1 else "5432"
        dbname = host_port_db[1] if len(host_port_db) > 1 else ""
        
        print(f"Connecting to: host={host}, port={port}, dbname={dbname}, user={username}")
        
        # Connect directly with psycopg2
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=username,
            password=password
        )
        
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()
        print(f"✅ PostgreSQL connection successful!")
        print(f"PostgreSQL version: {version[0]}")
        
        cur.close()
        conn.close()
        
    except ImportError:
        print("❌ psycopg2 package not installed. Install with: pip install psycopg2-binary")
    except Exception as e:
        print(f"❌ Direct PostgreSQL connection failed: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    test_db_connection()
    check_postgresql()