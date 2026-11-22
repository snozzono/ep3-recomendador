# Sistema de recomendación de productos — EP3 (ITY1102)

> **Estado: FAULTY — no está listo para demo.** Lo verificado hasta hoy:
> - Entrenamiento en SageMaker (`aws/02_run.py`) falló: los hyperparameters llegan como `-k 32` y el script solo aceptaba `--k`. Corregido en `aws/02_entrenar_sagemaker.py` (línea 57), **pendiente de relanzar y confirmar Completed**.
> - Sin verificar en vivo: Lambda/API Gateway de EP3, RabbitMQ (broker y consumidor), Docker build/compose, pruebas de carga (Locust), dashboard y Swagger.
> - `Recomendador.recomendar` en `servicio/` no excluye los ítems ya vistos (la Lambda sí).
> - Pruebas unitarias: 29 pasan en local (Python 3.12), pero no cubren el broker real.

API REST (FastAPI) que sirve recomendaciones por usuario, recibe interacciones y las publica en RabbitMQ.
Un consumidor lee la cola y registra los eventos; es el punto donde luego se actualizará el modelo.

## Estructura

```
EP3/
├── docker-compose.yml     # rabbitmq + api + consumidor
├── README.md
├── datos/                 # datos (no versionado por este servicio)
├── modelo/                # modelo.npz con matrices U y V (entrenado en otra etapa)
├── servicio/
│   ├── app.py             # API FastAPI (crear_app / app)
│   ├── modelo.py          # Recomendador (U @ V.T, top-n) y respaldo por popularidad
│   ├── mensajeria.py      # Publicador RabbitMQ con pika (cola "interacciones")
│   ├── consumidor.py      # Consumidor: escribe eventos en eventos.jsonl
│   ├── schemas.py         # Modelos Pydantic de entrada/salida
│   ├── requirements.txt
│   └── Dockerfile
└── tests/
    ├── pytest.ini
    ├── conftest.py        # fixtures y generación del modelo sintético
    ├── modelo_sintetico.npz
    ├── test_api.py
    ├── test_mensajeria_consumidor.py
    └── locustfile.py      # carga: GET /recomendar (4) y POST /interacciones (1)
```

## Ejecutar en local

Requiere Python 3.12 (igual que la imagen Docker).

```powershell
cd "EP3"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r servicio\requirements.txt
```

**Pruebas** (no requieren RabbitMQ: el publicador se mockea):

```powershell
python -m pytest tests -q
```

**API** (desde `servicio\`):

```powershell
cd servicio
$env:MODEL_PATH = "..\modelo\modelo.npz"          # opcional; este es el valor por defecto
$env:RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"
uvicorn app:app --reload --port 8000
```

Si `MODEL_PATH` no existe, la API arranca con el respaldo por popularidad (lee `servicio\eventos.jsonl`) y lo registra en el log.

**Consumidor** (con RabbitMQ levantado):

```powershell
cd servicio
python consumidor.py
```

**Carga** (Locust, con la API levantada):

```powershell
locust -f tests\locustfile.py --host http://localhost:8000
```

Variables opcionales: `USUARIOS_MAX` y `PRODUCTOS_MAX` (rangos de ids aleatorios, por defecto 1000).

## Docker

```powershell
docker compose up --build
```

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- RabbitMQ: AMQP en `5672`, panel de administración en http://localhost:15672 (`guest` / `guest`)

## Endpoints

| Método | Ruta | Descripción | Respuestas |
|---|---|---|---|
| GET | `/recomendar?usuario=N&n=5` | Top-n productos para el usuario | 200 `{usuario, recomendaciones, modelo}` · 404 usuario inexistente · 422 `n` fuera de 1–100 |
| POST | `/interacciones` | Body `{usuario, producto, rating (1–5), timestamp}`; publica en la cola `interacciones` | 202 `{estado: "aceptado"}` · 422 evento inválido · 503 RabbitMQ no disponible |
| GET | `/salud` | Estado del servicio | 200 `{estado: "ok"}` |
| GET | `/docs` | Swagger / OpenAPI interactivo | — |

## Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `MODEL_PATH` | `../modelo/modelo.npz` (relativo a `servicio/`) | Archivo `.npz` con claves `U` (usuarios × k) y `V` (productos × k) |
| `EVENTOS_PATH` | `servicio/eventos.jsonl` | Eventos del consumidor; también alimenta el respaldo por popularidad |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Conexión a RabbitMQ para API y consumidor |
