# week0/hello.py —— 环境自检：打印版本并确认在 venv 里
import sys

name = "毕榕霖(Bi Ronglin)"
version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
print(f"hello, {name} | Python {version}")
print(f"interpreter: {sys.executable}")