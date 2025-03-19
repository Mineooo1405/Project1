import subprocess
import time
import os

def run_test(data_type, count=3):
    print(f"\n{'='*60}")
    print(f"TESTING {data_type.upper()} DATA")
    print(f"{'='*60}")
    cmd = f"python send_robot_data.py --type {data_type} --count {count} --interval 0.5"
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True)
    time.sleep(1)
    return result.returncode == 0

def main():
    all_ok = True
    
    # Test all data types
    data_types = ["imu", "encoder", "trajectory", "pid"]
    for dt in data_types:
        if not run_test(dt):
            all_ok = False
            print(f"Test failed for {dt}")
    
    # View results in database
    print(f"\n{'='*60}")
    print(f"CHECKING DATABASE RECORDS")
    print(f"{'='*60}")
    subprocess.run("python view_database.py --type all --robot robot1 --limit 3", shell=True)
    
    if all_ok:
        print("\n✅ All tests completed successfully!")
    else:
        print("\n❌ Some tests failed - check the output above for details.")

if __name__ == "__main__":
    main()