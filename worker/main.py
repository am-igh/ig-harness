"""IG Harness worker. Phase 1 skeleton: idles. Scheduled jobs arrive in later phases."""
import time


def main() -> None:
    print("worker: started, idle (no jobs scheduled in Phase 1)", flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
