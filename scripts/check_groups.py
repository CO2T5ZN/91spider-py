"""验证分组提取"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scraper import parser  # noqa: E402

html = open(os.path.join(os.environ["TEMP"], "91porna_home_fresh.html"),
            encoding="utf-8", errors="ignore").read()
cats = parser.parse_home_categories(html)
groups = {}
for c in cats:
    groups.setdefault(c["group"], []).append(c["name"])
for g, names in groups.items():
    print(repr(g), "->", names)
