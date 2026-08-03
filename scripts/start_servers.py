import os
import sys
import subprocess
import time

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    backend_dir = os.path.join(root_dir, "backend")
    frontend_dir = os.path.join(root_dir, "frontend")

    print("[Pipeline.sh] Starting backend server (Flask) on port 5000...")
    backend_proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=backend_dir,
        env=dict(os.environ, PYTHONPATH=root_dir),
    )

    print("[Pipeline.sh] Starting frontend server (Vite) on port 3000...")
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=frontend_dir,
    )

    print("[Pipeline.sh] Both servers started successfully.")
    print("  - Backend API: http://localhost:5000")
    print("  - Frontend UI:  http://localhost:3000")
    print("Press Ctrl+C to terminate both servers.\n")

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                print("[Pipeline.sh] Backend process exited unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("[Pipeline.sh] Frontend process exited unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\n[Pipeline.sh] Stopping servers...")
    finally:
        for proc in (backend_proc, frontend_proc):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("[Pipeline.sh] Servers stopped.")

if __name__ == "__main__":
    main()
