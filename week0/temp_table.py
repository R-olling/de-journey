# 用途：打印 -40~100°F 对应的摄氏温度表，双列右对齐
def f_to_c(f: float) -> float:
    """华氏转摄氏：先减 32，再乘 5 除以 9"""
    return (f - 32) * 5 / 9

def classify_temp(c: float) -> str:
    """根据摄氏度返回温度等级"""
    if c < 10:
        return "cold"
    elif c < 25:
        return "mild"
    else:
        return "hot"

def main() -> None:
    # >10 = 宽度 10、右对齐（数字右对齐才好看）
    print(f"{'Fahrenheit':>10} | {'Celsius':>8}")
    print("-" * 21)
    # range(-40, 101, 10)：-40 到 100，步长 10，共 15 个数
    for f in range(-40, 101, 10):
        c = f_to_c(f)
        print(f"{f:>10} | {c:>8.1f}   {classify_temp(c)}")

if __name__ == "__main__":
    main()
