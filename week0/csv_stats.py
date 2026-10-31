# 用途：读 week0/data/temps.csv，算 temp_c 的行数/均值/最大/最小
import csv
from pathlib import Path

DATA = Path(__file__).parent / "data" / "temps.csv"

def main() -> None:
    values = []
    try:
        with open(DATA, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                values.append(float(row["temp_c"]))
    except FileNotFoundError:
        print("File 'temps.csv' not found.")
        return
    except UnicodeDecodeError:
        print("Error decoding 'temps.csv' file. Try encoding='gbk'")
        return

    n = len(values)
    mean = sum(values) / n if n > 0 else 0
    print(f"rows={n} mean={mean:.2f} max={max(values):.1f} min={min(values):.1f}")

if __name__ == "__main__":
    main()
