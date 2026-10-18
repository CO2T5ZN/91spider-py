"""检查下载产物与临时目录"""

import glob
import os

files = glob.glob(r"D:\python\video_spider\data\videos\AI*\*.ts")
sizes = [os.path.getsize(f) for f in files]
print("完成视频数:", len(files))
if sizes:
    print("总大小: %.1f MB" % (sum(sizes) / 1048576))
    print("最小/最大: %.1f / %.1f MB" % (min(sizes) / 1048576, max(sizes) / 1048576))
bad = [f for f in files if open(f, "rb").read(1) != b"\x47"]
print("TS头异常:", len(bad))
tmp = glob.glob(r"D:\python\video_spider\data\tmp\*")
print("tmp 残留目录:", len(tmp))
