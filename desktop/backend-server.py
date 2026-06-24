"""PyInstaller entry point for CScode backend server.

Compiled by PyInstaller into a standalone binary.
Usage: cscode-backend --port 8080 --host 127.0.0.1
"""
import argparse
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description="CScode Backend Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    try:
        from cscode.server.app import app
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
