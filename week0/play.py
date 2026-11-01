# n = 42
# x = 3.14
# s = "wuhan"
# ok = True
# nothing = None

# print(type(n),type(x),type(s),type(ok),type(nothing))
# print(f"{s}有{len(s)}个字母")
# print(f"{3.14159:.2f}")
# print(f"{'name':>8}|{'score':<6}")
# print(f"{0.5:.0%}")
# ----------------------------------------------
# temps = [21.5, 22.0, 19.8]
# temps.append(18.4)       
# temps[0] = 20.0             
# print(len(temps), max(temps), min(temps), sum(temps))
# city = {"name":"wuhan","temp_c":21.5}
# city["date"] = "2026-10-20"
# city["temp_c"] = 22.0
# print(city.get("humidity"))
# del city["date"]
# for k,v in city.items():
#     print(k,"=",v)
# ----------------------------------------------
# words = "a b a c b a".split()
# count = {}
# for w in words:
#     count[w] = count.get(w,0) + 1
# print(count)
# ----------------------------------------------
def f_to_c(f):
    "华氏度转摄氏度"
    return (f - 32) * 5 / 9

def classify_temp(c):
    "根据摄氏度返回温度等级"
    if c < 10:
        return "cold"
    elif c < 25:
        return "mild"
    else:
        return "hot"

def to_celsius(f:float,digits:int=1):

    return f"{f_to_c(f):.{digits}f}"

print(to_celsius(212),to_celsius(212,2))

try:
    with open("data/不存在.csv",encoding="utf-8") as f:
        print(f.read())
except FileNotFoundError:
    print("[ERR]文件不存在,检查路径")
except UnicodeDecodeError:
    print("[ERR]文件编码错误,检查编码格式，试试encoding='gbk'")









