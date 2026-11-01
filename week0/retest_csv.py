# 我要读/data/temps.csv，算 temp_c 的行数/均值/最大/最小
import csv
from pathlib import Path

DATA = Path(__file__).parent/"data"/"temps.csv"

def main() -> None:
    Values = []
    try:
        with open(DATA, newline= "", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                Values.append(float(row["temp_c"]))
    except FileNotFoundError:
        print("File 'temps.csv' not found.")
        return
    except UnicodeDecodeError:
        print("Error decoding 'temps.csv' file. Try encoding='gbk'")
        return
    n = len(Values)
    mean = sum(Values)/n if n>0 else 0
    print(f"rows={n} mean={mean:.2f} max={max(Values):.1f} min={min(Values):.1f}")

if __name__ =="__main__":
    main()