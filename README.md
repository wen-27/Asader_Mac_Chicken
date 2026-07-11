# ASADERO MC Bot Backend

Backend FastAPI del bot de pedidos por WhatsApp Cloud API de **ASADERO MC CHICKEN EXPRESS**.

Este proyecto corre **sin Docker**. Usa PostgreSQL como fuente de verdad, Redis para cache/idempotencia/locks, ChromaDB para busqueda semantica del catalogo y Gemini para lenguaje natural cuando las reglas locales no alcanzan.

## Documentos De Contexto

Antes de cambiar reglas funcionales, leer:

- `proposal.md`
- `spec.md`
- `design.md`
- `tasks.md`

## Variables Necesarias

Copia el archivo de ejemplo:

```bash
cp .env.example .env
```

En Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Completa `.env` con tus credenciales reales:

```env
APP_ENV=local
DATABASE_URL=postgresql+asyncpg://USUARIO:CLAVE@localhost:5433/asadero_mc
REDIS_URL=redis://localhost:6379/0
CHROMA_HOST=localhost
CHROMA_PORT=8001

WHATSAPP_ACCESS_TOKEN=token_permanente_o_temporal_de_meta
WHATSAPP_PHONE_NUMBER_ID=id_del_numero_de_whatsapp
WHATSAPP_VERIFY_TOKEN=un_secreto_largo_para_validar_el_webhook
WHATSAPP_GRAPH_API_VERSION=v23.0

LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.0-flash-lite
GOOGLE_API_KEY=api_key_de_gemini
GEMINI_API_KEY=api_key_de_gemini

OPENROUTESERVICE_API_KEY=api_key_de_openrouteservice
```

No subas `.env` a git.

## Ejecutar En Mac

### 1. Instalar requisitos

- Python 3.9.6
- Postgres.app
- Redis local en `.local/bin/redis-server`
- cloudflared en `.local/bin/cloudflared` si vas a probar WhatsApp con webhook local

### 2. Crear entorno e instalar dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### 3. Encender PostgreSQL

Abre Postgres.app y confirma que escuche en `localhost:5433`.

Crear la base si todavia no existe:

```bash
/Applications/Postgres.app/Contents/Versions/17/bin/createdb -h localhost -p 5433 -U wen asadero_mc
```

Si tu usuario no es `wen`, cambia el usuario en el comando y en `DATABASE_URL`.

### 4. Migrar y cargar catalogo

```bash
source .venv/bin/activate
python -m scripts.migrate
python -m scripts.seed
```

redis local

cd /Users/wen/Desktop/Asader_Mac_Chicken
.local/bin/redis-server --port 6379

### 5. Levantar todo

Primera vez o cuando quieras validar migraciones y seeders:

```bash
source .venv/bin/activate
python -m scripts.local_dev
```

Uso diario, si la base ya esta creada y cargada:

```bash
source .venv/bin/activate
python -m scripts.local_dev --skip-db-init
```

Esto deja:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- ChromaDB: `http://localhost:8001`
- Redis: `localhost:6379`

## Ejecutar En Windows

En Windows se recomienda levantar los servicios en terminales separadas.

### 1. Instalar requisitos

- Python 3.9.6
- PostgreSQL para Windows
- Redis compatible para Windows, por ejemplo Memurai o Redis en WSL
- cloudflared para Windows si vas a probar WhatsApp con webhook

PostgreSQL debe quedar escuchando en `localhost:5433` o debes ajustar el puerto en `DATABASE_URL`.

Redis debe quedar escuchando en `localhost:6379`.

### 2. Crear entorno e instalar dependencias

En PowerShell, desde la raiz del proyecto:

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Si PowerShell bloquea la activacion del entorno:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Cierra y abre PowerShell, vuelve a la carpeta del proyecto y activa:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Crear base de datos

Abre pgAdmin o SQL Shell y crea una base llamada:

```text
asadero_mc
```

Tambien puedes crearla por terminal si `createdb` esta disponible:

```powershell
createdb -h localhost -p 5433 -U TU_USUARIO asadero_mc
```

En `.env`, deja `DATABASE_URL` apuntando a esa base:

```env
DATABASE_URL=postgresql+asyncpg://TU_USUARIO:TU_CLAVE@localhost:5433/asadero_mc
```

### 4. Migrar y cargar catalogo

```powershell
.\.venv\Scripts\Activate.ps1
python -m scripts.migrate
python -m scripts.seed
```

### 5. Levantar servicios

Terminal 1, Redis:

```powershell
redis-server
```

Si usas Memurai, dejalo corriendo como servicio de Windows y no ejecutes este comando.

Terminal 2, ChromaDB:

```powershell
.\.venv\Scripts\Activate.ps1
chroma run --host localhost --port 8001 --path .\.chroma
```

Terminal 3, FastAPI:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Validar:

```powershell
curl http://localhost:8000/health
```

Abre Swagger:

```text
http://localhost:8000/docs
```

## Configurar WhatsApp Cloud API Con Tunel

Meta necesita una URL publica HTTPS para validar y llamar el webhook de WhatsApp.

### Opcion Recomendada: cloudflared

Mac:

```bash
.local/bin/cloudflared tunnel --url http://localhost:8000
```

Windows:

```powershell
cloudflared tunnel --url http://localhost:8000
```

El comando imprime una URL parecida a:

```text
https://algo.trycloudflare.com
```

En Meta Developers, configura:

- Callback URL: `https://TU_URL_PUBLICA/webhooks/whatsapp`
- Verify token: el mismo valor de `WHATSAPP_VERIFY_TOKEN`
- Campo suscrito: `messages`

### Opcion VS Code

Puedes usar port forwarding de VS Code solo si te entrega una URL publica HTTPS estable. Esa URL debe apuntar al puerto `8000` y se usa igual:

```text
https://TU_URL_PUBLICA/webhooks/whatsapp
```

## Comandos Utiles

Migraciones:

```bash
python -m scripts.migrate
```

Seeders:

```bash
python -m scripts.seed
```

Tests:

```bash
pytest
```

Reindexar catalogo semantico:

```bash
curl -X POST http://localhost:8000/admin/catalog/reindex-vector-store
```

Panel administrativo:

```bash
cd ../Asadero_Frontend
cp .env.example .env
npm install
npm run dev
```

El panel queda en:

```text
http://localhost:5173
```

La API debe estar corriendo en `http://localhost:8000`. Si cambia la URL, edita `../Frontend_Asadero/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Endpoints usados por el panel:

```text
GET   /api/admin/orders/incoming
GET   /api/admin/orders/accepted
GET   /api/admin/orders/rejected
GET   /api/admin/orders/{id}
PATCH /api/admin/orders/{id}/accept
PATCH /api/admin/orders/{id}/reject
PATCH /api/admin/orders/{id}/printed
```

Verificar webhook actual:

```bash
curl "https://TU_URL_PUBLICA/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=${WHATSAPP_VERIFY_TOKEN}&hub.challenge=test"
```

En Windows PowerShell:

```powershell
curl "https://TU_URL_PUBLICA/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=$env:WHATSAPP_VERIFY_TOKEN&hub.challenge=test"
```

## Flujo Diario Recomendado

Mac:

```bash
source .venv/bin/activate
python -m scripts.local_dev --skip-db-init
```

Windows:

1. Verifica que PostgreSQL este encendido.
2. Verifica que Redis este encendido.
3. Terminal 1: `chroma run --host localhost --port 8001 --path .\.chroma`
4. Terminal 2: `python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
5. Terminal 3: `cloudflared tunnel --url http://localhost:8000`
6. Si cambia la URL del tunel, actualiza el Callback URL en Meta Developers.

## Si Algo No Responde

1. Revisa `http://localhost:8000/health`.
2. Revisa `http://localhost:8000/docs`.
3. Revisa que Redis este en `localhost:6379`.
4. Revisa que Chroma este en `localhost:8001`.
5. Revisa que `DATABASE_URL` apunte a la base real.
6. Revisa la validacion del webhook:

```bash
curl "https://TU_URL_PUBLICA/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=${WHATSAPP_VERIFY_TOKEN}&hub.challenge=test"
```

7. Si cambiaste codigo y WhatsApp sigue igual, reinicia FastAPI.

## Notas De Produccion

- PostgreSQL es la fuente de verdad.
- Redis puede perder datos sin romper pedidos confirmados.
- ChromaDB solo guarda catalogo y aliases, no clientes ni pedidos.
- Gemini se usa solo cuando las reglas deterministicas no resuelven el mensaje.
- No hardcodear tokens, claves ni secretos en el codigo.
