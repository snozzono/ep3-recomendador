# Sistema de recomendación de productos — EP3 (ITY1102)

API REST (FastAPI) que sirve recomendaciones por usuario, recibe interacciones y las publica en RabbitMQ.
Un consumidor lee la cola y registra los eventos; es el punto donde luego se actualizará el modelo.

## Estado (verificado el 24-11-2026)

Entorno de la verificación: Windows, Python 3.12.10 (`.venv`), Docker 29.4.1. Todas las pruebas de esta tabla se ejecutaron en localhost; la salida clave se copió de la consola.

| Prueba | Resultado | Salida clave |
|---|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests -q` | OK | `47 passed, 1 warning` |
| API local · `GET /salud` | OK | 200 `{"estado":"ok"}` |
| API local · `GET /recomendar` sin clave / con clave | OK | 401 / 200 (`"modelo":"svd-als"`) |
| API local · `GET /recomendar` usuario inexistente | OK | 404 `El usuario 999999999 no existe` |
| API local · `GET /recomendar` con `n=0` | OK | 422 |
| API local · `POST /interacciones` sin RabbitMQ | OK (503 esperado) | 503 `No se pudo registrar la interacción; intente más tarde` |
| API local · `/docs`, `/dashboard`, `/openapi.json` | OK | 200 / 200 / 200 |
| Recomendador excluye vistos | OK | 4 usuarios (6 a 59 vistos cada uno), top-100 de cada uno: 0 productos ya vistos |
| `docker compose up -d --build` | OK | rabbitmq `healthy`; api y consumidor `Up` |
| Docker · `/salud`, `/recomendar` sin clave / con clave | OK | 200 · 401 · 200 |
| Docker · `POST /interacciones` (RabbitMQ arriba) | OK | 202 `{"estado":"aceptado"}` |
| Docker · consumidor | OK | `Evento registrado: usuario=AFNT6ZJCYQN3WDIKUSWHJDXNND2Q producto=B00EP3TEST1 rating=5.0` |
| Locust headless, 10 usuarios, 20 s (`RATE_LIMIT_POR_MINUTO=100000`) | OK | 246 peticiones, 0 fallos; p50 62 ms, p95 180 ms, p99 290 ms (agregado) |
| `docker compose down` | OK | 0 contenedores `ep3-*` activos |

Modelo: el job de SageMaker `ep3-svd-2026-11-24-15-45-45-251` está `Completed`. La Lambda y la API de AWS se probaron en una sesión anterior (401 sin clave, 200 con clave, 404 usuario inexistente, 400 sin `usuario`); **no se volvieron a ejecutar el 24-11-2026**.

Pruebas anteriores (no repetidas en esta verificación):

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
- **Carga anterior** (Locust, 20 usuarios, 30 s, `tests\resultados_locust_stats.csv`): 956 peticiones, 0 fallos, mediana 36 ms, p95 170 ms, p99 220 ms. Esa corrida usó `RATE_LIMIT_POR_MINUTO=100000`. Con el límite por defecto, otra corrida devolvió 429 en el 94 % de las peticiones (ese CSV no se guardó en el repo).
- **Esquema OpenAPI:** `docs\openapi.json` (lista `/salud`, `/recomendar` e `/interacciones`).

### Lo que queda fuera

- **Kafka:** no se usa. La mensajería es **RabbitMQ** (librería `pika`).
- **TLS:** no se implementa en el contenedor. En AWS lo termina API Gateway (HTTPS); en local el servicio responde en HTTP plano.
- **Modelo:** las métricas usan la implementación numpy de ALS (la de `aws/`), no la librería `implicit` que usa `modelo/ALS_eval.py`; las cifras de Precision@5 difieren ligeramente (0,0101 frente a 0,0100).

### Pendiente

- **RabbitMQ en AWS (EC2):** publicar y leer se probó una vez en una sesión anterior (`aws\06_probar_rabbitmq.sh`); no se repitió el 24-11-2026.
- **Arranque de Docker:** `rabbitmq-diagnostics ping` marca `healthy` antes de que el puerto AMQP 5672 acepte conexiones. En la primera prueba, `POST /interacciones` dio 503 (RabbitMQ aún no aceptaba conexiones) y, al esperar, 202. El consumidor tampoco conectó de inmediato: reintenta con espera creciente (16 s, 30 s…) y en la segunda prueba conectó tras ~1 min, consumió el evento y lo registró. No se cambió el compose; una mejora sería un healthcheck con `check_port_connectivity`.
- **Carga con el límite por defecto (60/min por IP):** no se midió de nuevo; la prueba de carga necesita `RATE_LIMIT_POR_MINUTO` alto.
- **Dashboard:** solo se comprobó que responde 200; no se probó en navegador.
- **Locust con CSV:** la verificación del 24-11-2026 se corrió sin `--csv`; los `tests\resultados_locust_*.csv` del repo son de la corrida anterior.
- **Documentos fuera de este README:** `aws\README.md` (línea 114) y `informe\EP3_Informe.md` todavía mencionan el estado FAULTY del paso 2; no se modificaron aquí.

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

## Ejecutar en localhost

Probado en Windows con Python 3.12.10 y Docker 29.4.1. Ejecutar desde la carpeta `EP3`. La clave `clave-de-ejemplo-cambiar` es un ejemplo: use la suya.

### 1. Entorno

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r servicio\requirements.txt
```

La instalación se probó sobre un `.venv` ya existente (`Requirement already satisfied` para las dependencias); la creación del venv con `py -3.12` se documenta como estándar.

### 2. Clave de API

Cree un archivo `.env` junto a `docker-compose.yml` (no se versiona) con una línea:

```
API_KEY=clave-de-ejemplo-cambiar
```

Docker Compose lo lee automáticamente. Uvicorn no lee `.env`: en local defina la clave en la sesión (paso 4).

### 3. Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Resultado esperado: `47 passed`. No requieren RabbitMQ: el publicador se mockea y las pruebas usan su propia clave.

### 4. API local

```powershell
cd servicio
$env:API_KEY = "clave-de-ejemplo-cambiar"
..\.venv\Scripts\python.exe -m uvicorn app:app --reload --port 8000
```

Si `MODEL_PATH` no existe, la API arranca con el respaldo por popularidad (lee `servicio\eventos.jsonl`) y lo registra en el log. Por defecto usa `..\modelo\modelo.npz`, que existe en el repo.

Con la API levantada, desde otra terminal (`curl.exe`, no `curl` de PowerShell):

```powershell
curl.exe -s -w " %{http_code}\n" http://127.0.0.1:8000/salud
curl.exe -s -w " %{http_code}\n" "http://127.0.0.1:8000/recomendar?usuario=AFNT6ZJCYQN3WDIKUSWHJDXNND2Q&n=3"
curl.exe -s -w " %{http_code}\n" -H "X-API-Key: clave-de-ejemplo-cambiar" "http://127.0.0.1:8000/recomendar?usuario=AFNT6ZJCYQN3WDIKUSWHJDXNND2Q&n=3"
```

Esperado: 200, 401 y 200. `AFNT6ZJCYQN3WDIKUSWHJDXNND2Q` existe en `modelo.npz`.

Para detener uvicorn use Ctrl+C. Con `--reload` queda un proceso hijo; si el puerto 8000 sigue ocupado, ciérrelo antes de volver a arrancar.

### 5. Consumidor

Dentro de Docker, el servicio `consumidor` ejecuta `python consumidor.py` (ver paso 6). Ejecutarlo fuera de Docker no se probó en esta verificación.

### 6. Docker

```powershell
docker compose up -d --build
curl.exe -s -w " %{http_code}\n" http://localhost:8000/salud
curl.exe -s -o NUL -w "%{http_code}\n" -H "X-API-Key: clave-de-ejemplo-cambiar" "http://localhost:8000/recomendar?usuario=AFNT6ZJCYQN3WDIKUSWHJDXNND2Q"
```

La clave de estos comandos debe ser la de `.env`. Para publicar una interacción, escriba el JSON en un archivo (en PowerShell el JSON inline dentro de `curl.exe -d` se rompe):

```powershell
[System.IO.File]::WriteAllText("$env:TEMP\evento.json", '{"usuario":"AFNT6ZJCYQN3WDIKUSWHJDXNND2Q","producto":"B00EP3TEST1","rating":5,"timestamp":1700000000}', (New-Object System.Text.UTF8Encoding $false))
curl.exe -s -w " %{http_code}\n" -X POST -H "X-API-Key: clave-de-ejemplo-cambiar" -H "Content-Type: application/json" --data-binary "@$env:TEMP\evento.json" http://localhost:8000/interacciones
docker compose logs consumidor --tail 20
docker compose down
```

Esperado: 200 y 401 en las consultas; `202 {"estado":"aceptado"}` al publicar; en el log del consumidor, `Evento registrado: usuario=... producto=B00EP3TEST1`.

- API: http://localhost:8000
- Dashboard: http://localhost:8000/dashboard (pide la clave en el formulario)
- Swagger: http://localhost:8000/docs (botón *Authorize* para la clave)
- RabbitMQ: AMQP en `5672`, panel de administración en http://localhost:15672 (`guest` / `guest`)

Si RabbitMQ aún no acepta conexiones tras el `healthy`, el primer `POST /interacciones` responde 503; repita el envío tras unos segundos. El consumidor puede tardar hasta ~1 min en conectar tras el arranque (ver Pendiente).

### 7. Carga (Locust)

Con la API levantada (local o Docker) y la misma clave. Para la carga, la API necesita un límite alto por IP; en Docker:

```powershell
$env:RATE_LIMIT_POR_MINUTO = "100000"
docker compose up -d api
Remove-Item Env:RATE_LIMIT_POR_MINUTO
```

Después:

```powershell
$env:API_KEY = "clave-de-ejemplo-cambiar"
.\.venv\Scripts\python.exe -m locust -f tests\locustfile.py --host http://127.0.0.1:8000 --headless -u 10 -r 5 -t 20s
```

La salida trae la tabla de peticiones y, al final, `Response time percentiles` (p50, p95, p99). Para guardar CSV agregue `--csv tests\resultados_locust`; eso sobrescribe los CSV versionados y no se ejecutó en esta verificación.

Usar `python -m locust`: `locust.exe` puede estar bloqueado por políticas de aplicaciones en Windows.

Variables opcionales del locustfile: `USUARIOS_MAX` y `PRODUCTOS_MAX` (rangos de ids aleatorios, por defecto 1000).

## Regenerar `docs/openapi.json`

Con la API levantada (local o Docker), exportar el esquema con la clave:

```powershell
curl.exe -H "X-API-Key: una-clave-larga" http://localhost:8000/openapi.json -o docs\openapi.json
```

Hay que repetirlo cada vez que cambie un endpoint. Usar `curl.exe`: en Windows PowerShell, la redirección `>` escribe UTF-16 y rompe el JSON. Este comando no se volvió a ejecutar en la verificación del 24-11-2026 (sobrescribiría `docs\openapi.json`); el `/openapi.json` sí respondió 200.

## Endpoints

| Método | Ruta | Descripción | Respuestas |
|---|---|---|---|
| GET | `/recomendar?usuario=<user_id>&n=5` | Top-n productos para el usuario, sin los ya vistos. Requiere `X-API-Key` | 200 `{usuario, recomendaciones: [{parent_asin, score}], modelo}` · 401 clave ausente o incorrecta · 404 usuario inexistente · 422 `n` fuera de 1–100 · 429 límite por IP excedido · 500 `API_KEY` no configurada |
| POST | `/interacciones` | Body `{usuario, producto (parent_asin), rating (1–5), timestamp}`; publica en la cola `interacciones`. Requiere `X-API-Key` | 202 `{estado: "aceptado"}` · 401 · 422 evento inválido · 429 · 503 RabbitMQ no disponible |
| GET | `/salud` | Estado del servicio (público) | 200 `{estado: "ok"}` |
| GET | `/dashboard` | Página HTML para consultar recomendaciones por user_id (público; pide la clave) | 200 |
| GET | `/docs` | Swagger / OpenAPI interactivo (público) | 200 |

Los códigos de la tabla se probaron en local y en Docker (ver Estado), salvo 429 y 500, que cubren los tests. En AWS, la Lambda responde 400 si falta `usuario` con clave válida (según `aws\README.md`).

## AWS

Todo se ejecuta en **AWS CloudShell** (us-east-1), en el orden de `aws\README.md`. Cada paso tiene un punto de control allí. No hay script `08_*`.

| Orden | Script | Qué hace |
|---|---|---|
| 0 | `00_preparar.sh` | Clona el repo en `~/ep3` y crea el venv `~/venv-sm` |
| 1 | `00_verificar.sh` | Muestra qué falta (dataset, job, modelos, Lambda/API) |
| 1b | `01_datos.sh` | Sube el dataset a S3 (solo si el bucket se vació) |
| 2 | `02_run.py` (usa `02_entrenar_sagemaker.py`) | Entrena ALS en SageMaker (`ep3-svd-*`) |
| 3 | `03_publicar_modelo.sh` | Publica el modelo en S3 (imprime `MODEL_KEY=`) |
| 4 | `04_lambda_api.sh` | Crea/actualiza la Lambda `ep3-recomendador` y la API `ep3-recomendador-api` (requiere `API_KEY`) |
| 5 | `05_rabbitmq_ec2.sh` | RabbitMQ en EC2 (opcional; requiere `MI_IP` y `RABBIT_PASS`) |
| 6 | `06_probar_rabbitmq.sh` | Prueba el broker (HTTP 15672 y AMQP publicar+leer) |
| 7 | `07_limpieza.sh` | Borra EC2, security group, API, Lambda y su log group (`CONFIRMAR=si`) |
| 9 | `09_evidencia.sh` | Llamadas HTTP y bloques `=== [N]` para capturas (requiere `API_KEY`) |

Recursos actuales:

- API: `ep3-recomendador-api`, id **`5uli1pw7qf`**. URL: `https://5uli1pw7qf.execute-api.us-east-1.amazonaws.com/recomendar`
- Lambda: `ep3-recomendador` (logs en CloudWatch `/aws/lambda/ep3-recomendador`)

La clave de la API no está en el repo: se pasa con `export API_KEY=...` en CloudShell, con el mismo valor que el `.env` local.

## Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `API_KEY` | sin valor (las rutas protegidas responden 500). En compose: `cambiar-esta-clave` | Clave que deben enviar los clientes en `X-API-Key` |
| `RATE_LIMIT_POR_MINUTO` | `60` | Peticiones máximas por minuto y por IP |
| `MODEL_PATH` | `../modelo/modelo.npz` (relativo a `servicio/`) | Archivo `.npz` con claves `U` (usuarios × k), `V` (productos × k), `user_ids`, `item_ids` (strings), `vistos_ptr` y `vistos` (CSR de vistos). Lo genera `aws/02_entrenar_sagemaker.py` como `modelo_svd.npz` (renombrar a `modelo.npz`) |
| `EVENTOS_PATH` | `servicio/eventos.jsonl` | Eventos del consumidor; también alimenta el respaldo por popularidad |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Conexión a RabbitMQ para API y consumidor |
