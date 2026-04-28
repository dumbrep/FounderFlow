"""
Helper: watches a directory and auto-restarts a server command on .py changes.
Usage: python _watcher.py <watch_dir> <command...>
"""
import sys
import watchfiles


def main():
    if len(sys.argv) < 3:
        print("Usage: python _watcher.py <watch_dir> <command...>")
        sys.exit(1)

    watch_dir = sys.argv[1]
    command = " ".join(sys.argv[2:])

    print(f"[watcher] Watching: {watch_dir}")
    print(f"[watcher] Command:  {command}")
    print(f"[watcher] Will auto-restart on .py file changes.\n")

    watchfiles.run_process(
        watch_dir,
        target=command,
        target_type="command",
        watch_filter=watchfiles.PythonFilter(),
        callback=lambda changes: print(
            f"\n[watcher] {len(changes)} file(s) changed — restarting..."
        ),
    )


if __name__ == "__main__":
    main()
