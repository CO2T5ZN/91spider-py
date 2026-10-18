"""检查构建产物中的文案"""

import glob

for f in glob.glob(r"D:\python\video_spider\frontend\dist\assets\index-*.js"):
    data = open(f, "rb").read()
    print(f.split("\\")[-1], len(data))
    print("  old(尚未实现):", "尚未实现".encode("utf-8") in data)
    print("  new(AES-128):", "AES-128".encode("utf-8") in data)
