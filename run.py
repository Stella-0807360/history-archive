import argparse
import os
import socket
import sys
import webbrowser

import uvicorn

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8000))


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def banner(ip):
    print("=" * 58)
    print("  历史资料智能抓取平台")
    print("=" * 58)
    print("  本机访问   : http://127.0.0.1:{}".format(PORT))
    print("  局域网访问 : http://{}:{}".format(ip, PORT))
    print("  公网访问   : 用内网穿透工具映射 {} 端口即可".format(PORT))
    print("  内网穿透示例:  cpolar http {}  或  ngrok http {}".format(PORT, PORT))
    print("=" * 58)
    print("  提示：首次使用请先在页面上设置访问口令（公网访问必备）")
    print("  手动登录流程：在页面点「打开浏览器登录」，电脑屏幕会弹出浏览器")
    print("=" * 58)


def main():
    parser = argparse.ArgumentParser(description="历史资料智能抓取平台")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    banner(lan_ip())
    if not args.no_browser:
        webbrowser.open("http://127.0.0.1:{}".format(args.port))
    uvicorn.run("app.main:app", host=args.host, port=args.port,
                reload=False, workers=1)


if __name__ == "__main__":
    main()
