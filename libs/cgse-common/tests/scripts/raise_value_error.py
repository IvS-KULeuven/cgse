import json
import sys
import time
import traceback


def main():
    time.sleep(1.0)

    try:
        raise ValueError("for testing purposes")
    except Exception as e:
        error_info = {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc()}
        print(json.dumps(error_info), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
