# Sistema de recomendación de productos — EP3 (ITY1102)

API REST (FastAPI) que sirve recomendaciones por usuario, recibe interacciones y las publica en RabbitMQ.
Un consumidor lee la cola y registra los eventos; es el punto donde luego se actualizará el modelo.

## Estado verificado

- **Pruebas unitarias y de API:** `python -m pytest tests -q` → **43 pasan** (Python 3.12, `.venv`). Incluyen los casos de seguridad (401 sin clave y con clave incorrecta, 200 con clave correcta, 429 al superar el límite).
- **Recomendador:** `Recomendador.recomendar` excluye los productos ya vistos en el entrenamiento; lo cubre `test_recomendar_excluye_productos_vistos`.
- **Docker:** `docker compose up -d --build` levanta rabbitmq, api y consumidor. Verificado: `/recomendar` sin clave → 401, con clave → 200; `/salud` → 200; `/dashboard` → 200; `/interacciones` sin clave → 401, con clave → 202.
- **Carga (Locust, 20 usuarios, 30 s, con clave):** `tests\resultados_locust_stats.csv`: 956 peticiones, 0 fallos, mediana agregada 36 ms, p95 170 ms, p99 220 ms, 32,5 req/s. Esa corrida usó `RATE_LIMIT_POR_MINUTO=100000`, porque 20 usuarios desde una misma IP superan el límite por defecto (60/min). Con el límite por defecto, una corrida de prueba devolvió 429 en el 94 % de las peticiones (ese CSV no se guardó en el repo).
- **Métricas de clasificación** (`modelo\metricas_clasificacion.py` → `modelo\metricas_clasificacion_resultados.txt`):

  Partición 80/20 con semilla 42 (train 330 358, test 82 589), 36 454 usuarios con al menos un ítem relevante en test (rating ≥ 4), 942 019 848 candidatos (ítems no vistos en train). ALS numpy de `aws/02_entrenar_sagemaker.py` con k=32.

  | Métrica | ALS | Popularidad (baseline) |
  |---|---|---|
  | TP / FP | 1 836 / 180 434 | 835 / 181 435 |
  | FN / TN | 69 216 / 941 768 362 | 70 217 / 941 767 361 |
  | Accuracy | 0,999735 | 0,999733 |
  | Precision | 0,010073 | 0,004581 |
  | Recall | 0,025840 | 0,011752 |
  | F1 | 0,014495 | 0,006592 |
  | Precision@5 | 0,0101 | 0,0046 |
  | Recall@5 (media por usuario) | 0,0269 | 0,0125 |

  La accuracy está dominada por los negativos (TN); por eso el criterio útil es precision, recall y F1.
- **Esquema OpenAPI:** `docs\openapi.json` (lista `/salud`, `/recomendar` e `/interacciones`).

### Lo que queda fuera

- **Kafka:** no se usa. La mensajería es **RabbitMQ** (librería `pika`).
- **TLS:** no se implementa en el contenedor. En AWS lo termina API Gateway (HTTPS); en local el servicio responde en HTTP plano.
- **AWS (SageMaker, Lambda/API Gateway, RabbitMQ en EC2):** no re-verificado en esta entrega. Las pruebas en vivo son locales con Docker Compose.
- **Modelo:** las métricas usan la implementación numpy de ALS (la de `aws/`), no la librería `implicit` que usa `modelo/ALS_eval.py`; las cifras de Precision@5 difieren ligeramente (0,0101 frente a 0,0100).

## Seguridad

- **Autenticación:** `/recomendar` e `/interacciones` exigen la cabecera `X-API-Key`. Sin clave o con clave incorrecta responden **401**. Públicas: `/salud`, `/docs`, `/openapi.json` y `/dashboard`. El dashboard tiene un campo "Clave API" que envía la cabecera.
- **Clave:** variable de entorno `API_KEY`. Si no está definida, las rutas protegidas responden **500** con un mensaje claro y la API sigue arrancando. La comparación usa `hmac.compare_digest`.
- **Valor por defecto del compose:** `API_KEY=${API_KEY:-cambiar-esta-clave}`. **Cámbiela antes de desplegar.** Puede definirla en un archivo `.env` junto a `docker-compose.yml` (está en `.gitignore`).
- **Rate limiting:** máximo **60 peticiones por minuto por IP** (variable `RATE_LIMIT_POR_MINUTO`). Excedido, responde **429** con cabecera `Retry-After`. Se implementa sin librerías externas: ventana deslizante en memoria (`LimitadorIP` en `servicio/app.py`), porque `slowapi` no está en `requirements.txt`. Cuenta todas las rutas, incluidas las respuestas 401. Limitaciones: el contador es por proceso (no se comparte entre réplicas) y, detrás de un proxy, la IP que se cuenta es la del proxy.
- **TLS:** fuera del contenedor. En AWS, API Gateway termina HTTPS; en local no hay TLS.

## Estructura

```
EP3/
├── docker-compose.yml     # rabbitmq + api + consumidor
├── README.md
├── datos/                 # datos (no versionado)
├── docs/
│   └── openapi.json       # esquema OpenAPI exportado de la API
├── modelo/
│   ├── modelo.npz         # matrices U y V (entrenado en otra etapa; no versionado)
│   ├── ALS_eval.py        # evaluación de ranking con implicit (Precision@5)
│   ├── baseline_eval.py   # SVD y popularidad
│   └── metricas_clasificacion.py   # TP/FP/FN/TN, accuracy, precision, recall, F1
├── servicio/
│   ├── app.py             # API FastAPI (crear_app / app): autenticación y rate limit
│   ├── modelo.py          # Recomendador (U @ V.T, top-n sin vistos) y respaldo por popularidad
│   ├── mensajeria.py      # Publicador RabbitMQ con pika (cola "interacciones")
│   ├── consumidor.py      # Consumidor: escribe eventos en eventos.jsonl
│   ├── schemas.py         # Modelos Pydantic de entrada/salida
│   ├── static/dashboard.html
│   ├── requirements.txt
│   └── Dockerfile
└── tests/
    ├── pytest.ini
    ├── conftest.py        # fixtures y generación del modelo sintético
    ├── modelo_sintetico.npz
    ├── test_api.py
    ├── test_mensajeria_consumidor.py
    ├── locustfile.py      # carga: GET /recomendar (4) y POST /interacciones (1), con X-API-Key
    └── resultados_locust_*.csv
```

## Ejecutar en local

Requiere Python 3.12 (igual que la imagen Docker).

```powershell
cd "EP3"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r servicio\requirements.txt
```

**Pruebas** (no requieren RabbitMQ: el publicador se mockea y las pruebas usan su propia clave):

```powershell
python -m pytest tests -q
```

**API** (desde `servicio\`):

```powershell
cd servicio
$env:API_KEY = "una-clave-larga"                  # obligatoria para /recomendar e /interacciones
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

**Carga** (Locust, con la API levantada y la misma `API_KEY`):

```powershell
$env:API_KEY = "una-clave-larga"
$env:RATE_LIMIT_POR_MINUTO = "100000"            # solo para carga: con 60/min desde una IP casi todo sale 429
python -m locust -f tests\locustfile.py --host http://localhost:8000 --headless -u 20 -r 20 -t 30s --csv tests\resultados_locust --only-summary
```

Usar `python -m locust`: `locust.exe` puede estar bloqueado por políticas de aplicaciones en Windows.

Variables opcionales del locustfile: `USUARIOS_MAX` y `PRODUCTOS_MAX` (rangos de ids aleatorios, por defecto 1000).

## Docker

```powershell
# .env (no versionado) con la clave real:
#   API_KEY=una-clave-larga
docker compose up -d --build
```

- API: http://localhost:8000
- Dashboard: http://localhost:8000/dashboard (pide la clave en el formulario)
- Swagger: http://localhost:8000/docs (botón *Authorize* para la clave)
- RabbitMQ: AMQP en `5672`, panel de administración en http://localhost:15672 (`guest` / `guest`)

## Regenerar `docs/openapi.json`

Con la API levantada (local o Docker), exportar el esquema con la clave:

```powershell
curl.exe -H "X-API-Key: una-clave-larga" http://localhost:8000/openapi.json -o docs\openapi.json
```

Hay que repetirlo cada vez que cambie un endpoint. Usar `curl.exe`: en Windows PowerShell, la redirección `>` escribe UTF-16 y rompe el JSON.

## Endpoints

| Método | Ruta | Descripción | Respuestas |
|---|---|---|---|
| GET | `/recomendar?usuario=<user_id>&n=5` | Top-n productos para el usuario, sin los ya vistos. Requiere `X-API-Key` | 200 `{usuario, recomendaciones: [{parent_asin, score}], modelo}` · 401 clave ausente o incorrecta · 404 usuario inexistente · 422 `n` fuera de 1–100 · 429 límite por IP excedido · 500 `API_KEY` no configurada |
| POST | `/interacciones` | Body `{usuario, producto (parent_asin), rating (1–5), timestamp}`; publica en la cola `interacciones`. Requiere `X-API-Key` | 202 `{estado: "aceptado"}` · 401 · 422 evento inválido · 429 · 503 RabbitMQ no disponible |
| GET | `/salud` | Estado del servicio (público) | 200 `{estado: "ok"}` |
| GET | `/dashboard` | Página HTML para consultar recomendaciones por user_id (público; pide la clave) | 200 |
| GET | `/docs` | Swagger / OpenAPI interactivo (público) | — |

## Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `API_KEY` | sin valor (las rutas protegidas responden 500). En compose: `cambiar-esta-clave` | Clave que deben enviar los clientes en `X-API-Key` |
| `RATE_LIMIT_POR_MINUTO` | `60` | Peticiones máximas por minuto y por IP |
| `MODEL_PATH` | `../modelo/modelo.npz` (relativo a `servicio/`) | Archivo `.npz` con claves `U` (usuarios × k), `V` (productos × k), `user_ids`, `item_ids` (strings), `vistos_ptr` y `vistos` (CSR de vistos). Lo genera `aws/02_entrenar_sagemaker.py` como `modelo_svd.npz` (renombrar a `modelo.npz`) |
| `EVENTOS_PATH` | `servicio/eventos.jsonl` | Eventos del consumidor; también alimenta el respaldo por popularidad |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Conexión a RabbitMQ para API y consumidor |
