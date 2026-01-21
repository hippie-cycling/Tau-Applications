# 🐧 Tau Testnet Node Setup Guide (Linux)

**OS:** Ubuntu 20.04+ / Debian 11+

**Goal:** Run a Python-based consensus node with a Dockerized Tau logic engine.

### 1. Install System Dependencies

Update your system and install the required tools for building cryptography libraries and managing containers.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-dev libgmp-dev docker.io build-essential

```

### 2. Configure Docker Permissions

Add your user to the Docker group to avoid using `sudo` for every command.

```bash
sudo usermod -aG docker $USER
newgrp docker

```

*Verification:* Run `docker ps`. If it prints a header without errors, you are ready.

### 3. Build the Logic Engine (`tau-lang`)

The node uses a Docker container to execute Tau logic. We must build this image first.

1. **Clone the repo:**
```bash
cd ~
git clone https://github.com/IDNI/tau-lang.git
cd tau-lang

```



3. **Build the Image:**
Target the Linux runner stage.
```bash
docker build --target runner -t tau .

```



### 4. Install the Node Software (`tau-testnet`)

1. **Clone the repo:**
```bash
cd ~
git clone https://github.com/IDNI/tau-testnet.git
cd tau-testnet

```


2. **Setup Python Environment:**
```bash
python3 -m venv venv
source venv/bin/activate

```


3. **Install Dependencies:**
```bash
pip install --upgrade pip
pip install -r requirements.txt

```


4. **Fix Permissions:**
Make the genesis file executable so Docker can run it.
```bash
chmod +x genesis.tau

```



### 5. Run the Node

With the virtual environment active:

```bash
python server.py

```

---

---

