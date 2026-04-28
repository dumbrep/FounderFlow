"""
Script to run all MCP servers in separate terminal windows.
Each terminal activates the virtual environment before running the server.
"""

import subprocess
import os
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.absolute()
VENV_ACTIVATE = PROJECT_ROOT / "venv" / "Scripts" / "Activate.ps1"
VENV_PYTHON = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
SERVERS_DIR = PROJECT_ROOT / "servers"

# List of all server files to run
SERVERS = [
    "email_server.py",
    "hiring_server.py",
    "instagram_server.py",
    "linkedIn_Mcpserver.py",
    "meet_schedule_server.py",
    "lead_gen/lead_gen_server.py"
]

def _watch_dirs_for_server(server_file):
    """Return the directories to watch for a given server file."""
    if "lead_gen" in server_file:
        return str(SERVERS_DIR / "lead_gen")
    return str(SERVERS_DIR)


WATCHER_SCRIPT = PROJECT_ROOT / "_watcher.py"


def run_server_in_new_terminal(server_file):
    """
    Launch a server in a new PowerShell terminal with venv activated.
    Uses _watcher.py + watchfiles for auto-reload on file changes.

    Args:
        server_file: Name of the server file to run (can include subdirectory)
    """
    server_path = SERVERS_DIR / server_file
    # Extract server name from file path (handle subdirectories)
    server_name = Path(server_file).stem.replace("_server", "").replace("_", " ").title()

    # Special handling for lead_gen server (uses relative imports, must run as module)
    if "lead_gen" in server_file:
        python_command = f'"{VENV_PYTHON}" -m servers.lead_gen.lead_gen_server'
    else:
        python_command = f'"{VENV_PYTHON}" "{server_path}"'

    watch_dir = _watch_dirs_for_server(server_file)

    # PowerShell command to run the watcher helper with venv python
    command = (
        f'powershell -NoExit -Command "'
        f'Write-Host \"Starting {server_name} Server [auto-reload]...\" -ForegroundColor Green; '
        f'Set-Location \"{PROJECT_ROOT}\"; '
        f'\"{VENV_PYTHON}\" \"{WATCHER_SCRIPT}\" \"{watch_dir}\" {python_command}'
        f'"'
    )

    try:
        # Start new PowerShell window
        subprocess.Popen(
            command,
            shell=True,
            cwd=str(PROJECT_ROOT)
        )
        print(f"✓ Launched {server_name} Server in new terminal (auto-reload enabled)")
    except Exception as e:
        print(f"✗ Failed to launch {server_name} Server: {e}")

def main():
    """Main function to launch all servers."""
    print("=" * 60)
    print("FounderFlow - Server Launcher")
    print("=" * 60)
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Virtual Environment: {VENV_ACTIVATE}")
    print(f"Servers Directory: {SERVERS_DIR}")
    print("=" * 60)
    print(f"Launching {len(SERVERS)} servers in separate terminals...\n")
    
    # Check if venv exists
    if not VENV_ACTIVATE.exists():
        print(f"⚠ Warning: Virtual environment not found at {VENV_ACTIVATE}")
        print("Please ensure the virtual environment is set up correctly.")
        return
    
    # Check if servers directory exists
    if not SERVERS_DIR.exists():
        print(f"✗ Error: Servers directory not found at {SERVERS_DIR}")
        return
    
    # Launch each server
    for server_file in SERVERS:
        server_path = SERVERS_DIR / server_file
        if server_path.exists():
            run_server_in_new_terminal(server_file)
        else:
            print(f"⚠ Warning: {server_file} not found, skipping...")
    
    print("\n" + "=" * 60)
    print("All servers launched successfully! (auto-reload enabled)")
    print("Each server is running in its own terminal window.")
    print("Editing any .py file in servers/ will auto-restart that server.")
    print("Close the terminal windows to stop the servers.")
    print("=" * 60)

if __name__ == "__main__":
    main()
