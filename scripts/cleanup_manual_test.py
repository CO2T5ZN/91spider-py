"""清理插件测试数据（保留正常功能状态）"""

import glob
import os
import shutil

import requests

API = "http://127.0.0.1:8765/api"

# 确认 33862 成片存在
files = glob.glob(r"D:\python\video_spider\data\videos\手动提交\*.ts")
for f in files:
    print("成片:", os.path.basename(f), "%.1f MB" % (os.path.getsize(f) / 1048576),
          "head=" + open(f, "rb").read(1).hex())

# 删除 3 条测试视频记录与文件
import sqlite3
conn = sqlite3.connect(r"D:\python\video_spider\data\spider.db")
ids = [r[0] for r in conn.execute(
    "SELECT id FROM videos WHERE video_key IN ('33862','33863','18917711096')").fetchall()]
print("删除测试记录:", ids)
conn.execute("DELETE FROM segments WHERE video_id IN (%s)" % ",".join("?" * len(ids)), ids)
conn.execute("DELETE FROM videos WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)
conn.commit()
conn.close()
shutil.rmtree(r"D:\python\video_spider\data\videos\手动提交", ignore_errors=True)
print("已清理测试成片目录")
