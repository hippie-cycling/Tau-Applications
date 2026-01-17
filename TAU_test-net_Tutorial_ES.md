# 🐧 Guía de Configuración del Nodo Tau Testnet (Linux)

**SO:** Ubuntu 20.04+ / Debian 11+
**Objetivo:** Ejecutar un nodo de consenso basado en Python con un motor lógico (Tau) dockerizado.

### 1. Instalar Dependencias del Sistema

Actualiza tu sistema e instala las herramientas necesarias para compilar librerías de criptografía y gestionar contenedores.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-dev libgmp-dev docker.io build-essential

```

### 2. Configurar Permisos de Docker

Añade tu usuario al grupo de Docker para evitar usar `sudo` en cada comando.

```bash
sudo usermod -aG docker $USER
newgrp docker

```

*Verificación:* Ejecuta `docker ps`. Si imprime un encabezado sin errores, estás listo.

### 3. Construir el Motor Lógico (`tau-lang`)

El nodo utiliza un contenedor Docker para ejecutar la lógica de Tau. Debemos construir esta imagen primero.

1. **Clonar el repositorio:**
```bash
cd ~
git clone https://github.com/IDNI/tau-lang.git
cd tau-lang

```



3. **Construir la Imagen:**
Apunta a la etapa runner de Linux.
```bash
docker build --target runner -t tau .

```



### 4. Instalar el Software del Nodo (`tau-testnet`)

1. **Clonar el repositorio:**
```bash
cd ~
git clone https://github.com/IDNI/tau-testnet.git
cd tau-testnet

```


2. **Configurar el Entorno Python:**
```bash
python3 -m venv venv
source venv/bin/activate

```


3. **Instalar Dependencias:**
```bash
pip install --upgrade pip
pip install -r requirements.txt

```


4. **Arreglar Permisos:**
Haz que el archivo génesis sea ejecutable para que Docker pueda correrlo.
```bash
chmod +x genesis.tau

```



### 5. Ejecutar el Nodo

Con el entorno virtual activo:

```bash
python server.py

```

---

---
