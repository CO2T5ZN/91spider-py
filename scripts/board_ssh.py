"""开发板 SSH 助手：连接信息从项目根 board.json 读取，支持多板。

用法（在项目根执行）:
  uv run --with paramiko python scripts/board_ssh.py run "uname -a"           # 默认板（board.json 的 default）
  uv run --with paramiko python scripts/board_ssh.py @n205 run "uname -a"     # 指定板（@板名）
  uv run --with paramiko python scripts/board_ssh.py sudo "apt-get -y install curl"
  uv run --with paramiko python scripts/board_ssh.py put <本地> <远程>         # 上传文件
  uv run --with paramiko python scripts/board_ssh.py get <远程> <本地>         # 下载文件
退出码为远程命令退出码；put/get 成功返回 0。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parent.parent
CFG_FILE = json.loads((ROOT / "board.json").read_text(encoding="utf-8"))


def pick_cfg(argv: list[str]) -> tuple[dict, list[str]]:
    args = list(argv)
    name = CFG_FILE.get("default")
    if args and args[0].startswith("@"):
        name = args[0][1:]
        args = args[1:]
    boards = CFG_FILE["boards"]
    if name not in boards:
        print(f"board '{name}' not in board.json (have: {', '.join(boards)})")
        sys.exit(2)
    return boards[name], args


def connect(cfg: dict) -> paramiko.SSHClient:
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(
        cfg["host"], port=cfg.get("port", 22), username=cfg["user"],
        password=cfg["password"], timeout=15, banner_timeout=15, auth_timeout=15,
    )
    return cli


def run(cli: paramiko.SSHClient, cfg: dict, cmd: str, sudo: bool = False) -> int:
    if sudo:
        cmd = f"sudo -S -p '' {cmd}"
    stdin, stdout, stderr = cli.exec_command(cmd)
    if sudo:
        stdin.write(cfg["password"] + "\n")
        stdin.flush()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    if out:
        sys.stdout.write(out)
    if err:
        sys.stdout.write("[stderr] " + err)
    return stdout.channel.recv_exit_status()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg, args = pick_cfg(sys.argv[1:])
    if not args:
        print(__doc__)
        return 2
    cli = connect(cfg)
    try:
        action, rest = args[0], args[1:]
        if action == "run" and rest:
            return run(cli, cfg, rest[0])
        if action == "sudo" and rest:
            return run(cli, cfg, rest[0], sudo=True)
        if action == "put" and len(rest) == 2:
            sftp = cli.open_sftp()
            sftp.put(rest[0], rest[1])
            print(f"uploaded {rest[0]} -> {rest[1]}")
            return 0
        if action == "get" and len(rest) == 2:
            sftp = cli.open_sftp()
            sftp.get(rest[0], rest[1])
            print(f"downloaded {rest[0]} -> {rest[1]}")
            return 0
        print(__doc__)
        return 2
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(main())
