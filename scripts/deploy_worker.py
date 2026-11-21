import os
import sys
import time
import io
import tarfile
import paramiko
import requests

SSH_HOST = "192.168.29.94"
SSH_PORT = 8022
SSH_USER = "u0_a162"
SSH_PASS = "ubuntu"
REMOTE_REPO_DIR = "/root/Gemini-AI-chatbot"
REMOTE_VENV_DIR = "/root/Gemini-AI-chatbot/venv"

def get_ssh_client():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS, timeout=30)
    return ssh

def exec_termux(cmd, timeout=60):
    ssh = get_ssh_client()
    try:
        print(f"\n[RUN TERMUX]: {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        exit_status = stdout.channel.recv_exit_status()
        if out:
            print(f"[STDOUT]: {out.strip()}")
        if err:
            print(f"[STDERR]: {err.strip()}")
        return exit_status, out, err
    finally:
        ssh.close()

def exec_proot(cmd, timeout=120):
    import base64
    b64 = base64.b64encode(cmd.encode('utf-8')).decode('ascii')
    full_cmd = f"proot-distro login ubuntu -- bash -c 'unset ANDROID_DATA ANDROID_ROOT; echo {b64} | base64 -d | bash'"
    return exec_termux(full_cmd, timeout=timeout)

def write_remote_file(content: str, remote_path: str):
    import base64
    b64 = base64.b64encode(content.encode('utf-8')).decode('ascii')
    cmd = f'echo "{b64}" | base64 -d > {remote_path}'
    return exec_proot(cmd)

def upload_local_dir_as_tar(local_dir: str, remote_dir: str):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for root, dirs, files in os.walk(local_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, local_dir)
                tar.add(full_path, arcname=rel_path)
    buf.seek(0)
    data = buf.read()

    ssh = get_ssh_client()
    try:
        sftp = ssh.open_sftp()
        with sftp.file("transfer_dist.tar.gz", "wb") as f:
            f.write(data)
        sftp.close()
        print("Uploaded transfer_dist.tar.gz to Termux home")
    finally:
        ssh.close()

    exec_proot(f"mkdir -p {remote_dir} && tar -xzf /data/data/com.termux/files/home/transfer_dist.tar.gz -C {remote_dir}")
    print(f"Extracted dist to {remote_dir}")

def get_env_content():
    local_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
    lines = []
    if os.path.exists(local_env_path):
        with open(local_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("DATABASE_PATH="):
                    lines.append("DATABASE_PATH=/root/Gemini-AI-chatbot/backend/chatbot.db")
                elif line.startswith("ALLOWED_ORIGINS="):
                    lines.append('ALLOWED_ORIGINS=["http://localhost:5173","http://localhost:8081","http://192.168.29.94:8081","http://192.168.29.94:5173","http://192.168.29.94","*"]')
                else:
                    lines.append(line)
    return "\n".join(lines) + "\n"

def deploy():
    print("=== Step 1: Update Repo on Worker ===")
    exec_proot(f"""
        cd {REMOTE_REPO_DIR} && git fetch origin main && git checkout main && git reset --hard origin/main
    """)

    print("=== Step 2: Configure .env ===")
    env_content = get_env_content()
    write_remote_file(env_content, f"{REMOTE_REPO_DIR}/backend/.env")

    print("=== Step 2.5: Test App Import ===")
    exec_proot(f"""
        cd {REMOTE_REPO_DIR}/backend && {REMOTE_VENV_DIR}/bin/python3 -c "import app.main; print('APP_LOAD_SUCCESS:', app.main.app)"
    """)

    print("=== Step 3: Transfer Frontend Dist Assets ===")
    local_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
    if os.path.exists(local_dist):
        upload_local_dir_as_tar(local_dist, f"{REMOTE_REPO_DIR}/frontend/dist")

    print("=== Step 4: Configure Combined Gateway Nginx ===")
    gateway_conf = """events {
    worker_connections 512;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    client_max_body_size 50M;

    # Gzip Compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css text/xml application/json application/javascript application/rss+xml application/atom+xml image/svg+xml;

    # ==========================================
    # Gemini AI Chatbot Gateway (Port 8081)
    # ==========================================
    server {
        listen 8081;
        server_name _;

        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;

        location / {
            root /root/Gemini-AI-chatbot/frontend/dist;
            index index.html index.htm;
            try_files $uri $uri/ /index.html;
        }

        location /health {
            proxy_pass http://127.0.0.1:8001/health;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /api/ {
            proxy_pass http://127.0.0.1:8001;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            proxy_buffering off;
            proxy_cache off;
            chunked_transfer_encoding on;

            proxy_read_timeout 120s;
            proxy_send_timeout 120s;
            proxy_connect_timeout 60s;
        }
    }

    # ==========================================
    # Pariksha Copilot Gateway (Port 8082)
    # ==========================================
    server {
        listen 8082;
        server_name _;

        root /root/pariksha-copilot/frontend/dist;
        index index.html;

        location / {
            try_files $uri $uri/ /index.html;
        }

        location /api/ {
            proxy_pass http://127.0.0.1:8000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_read_timeout 180s;
        }

        location /health {
            proxy_pass http://127.0.0.1:8000/health;
        }

        location /uploads/ {
            proxy_pass http://127.0.0.1:8000;
        }
    }
}
"""
    write_remote_file(gateway_conf, "/etc/nginx/sites-available/gateway.conf")

    print("=== Step 5: Create start_services.sh for Gemini AI Chatbot ===")
    start_services_sh = """#!/bin/bash
mkdir -p /var/log/gemini-chatbot
chmod 755 /root
chmod -R 755 /root/Gemini-AI-chatbot

# 1. Stop old instances
pkill -f "uvicorn.*8001" 2>/dev/null || true
sleep 1

# 2. Start Gemini-AI-chatbot Backend on 127.0.0.1:8001
echo "Starting Gemini AI Chatbot Backend on port 8001..."
cd /root/Gemini-AI-chatbot/backend
nohup /root/Gemini-AI-chatbot/venv/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001 > /var/log/gemini-chatbot/backend.log 2>&1 &

# 3. Wait for backend to be responsive on 8001
echo "Waiting for backend on 127.0.0.1:8001..."
BACKEND_OK=0
for i in $(seq 1 40); do
    if curl -s -f http://127.0.0.1:8001/health >/dev/null 2>&1; then
        echo "Backend is READY on 127.0.0.1:8001 (took ${i}s)"
        BACKEND_OK=1
        break
    fi
    sleep 1
done

if [ $BACKEND_OK -eq 0 ]; then
    echo "ERROR: Backend failed to start. Last log entries:"
    cat /var/log/gemini-chatbot/backend.log | tail -n 30
    exit 1
fi

# 4. Restart Nginx with the combined gateway.conf
echo "Applying Nginx Gateway configuration..."
pkill -9 nginx 2>/dev/null || true
sleep 1
nginx -c /etc/nginx/sites-available/gateway.conf

# 5. Check health via Nginx on port 8081
echo "Checking Gemini Chatbot Gateway on port 8081..."
for i in $(seq 1 10); do
    if curl -s -f http://127.0.0.1:8081/health >/dev/null 2>&1; then
        echo "SUCCESS: Gemini AI Chatbot Gateway is ONLINE at http://0.0.0.0:8081"
        curl -s http://127.0.0.1:8081/health
        echo ""
        break
    fi
    sleep 1
done

echo "Streaming logs from Gemini AI Chatbot..."
tail -f /var/log/gemini-chatbot/backend.log
"""
    write_remote_file(start_services_sh, f"{REMOTE_REPO_DIR}/start_services.sh")
    exec_proot(f"chmod +x {REMOTE_REPO_DIR}/start_services.sh")

    print("=== Step 6: Create Launcher & Run in Termux Tmux Session ===")
    launcher = """#!/data/data/com.termux/files/usr/bin/bash
proot-distro login ubuntu -- env -i HOME=/root PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin bash /root/Gemini-AI-chatbot/start_services.sh
"""
    import base64
    b64_launcher = base64.b64encode(launcher.encode('utf-8')).decode('ascii')
    exec_termux(f'echo "{b64_launcher}" | base64 -d > ~/run_gemini.sh && chmod +x ~/run_gemini.sh')

    exec_proot("rm -f /var/log/gemini-chatbot/backend.log")
    exec_termux("tmux kill-session -t gemini_chatbot 2>/dev/null || true")
    exec_termux("tmux new-session -d -s gemini_chatbot ~/run_gemini.sh")

    print("Waiting 12s for services to boot...")
    time.sleep(12)

    print("Checking active tmux sessions:")
    exec_termux("tmux list-sessions")

    print("Checking backend log output:")
    exec_proot("cat /var/log/gemini-chatbot/backend.log")

    print("=== Step 7: Verify Port 8081 Local and Remote ===")
    exec_proot("curl -s http://127.0.0.1:8081/health")

if __name__ == "__main__":
    deploy()
