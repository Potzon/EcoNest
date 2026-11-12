# EcoNest – Backend (Bloque A)

API REST + base de datos + Grafana para recibir y servir las detecciones de palomas de las Raspberry Pi.

## Arrancar

```bash
cp .env.example .env      # y cambia todos los valores
docker compose up --build
```

- API: http://localhost:8000 (documentación interactiva en `/docs`)
- Grafana: http://localhost:3000 (usuario `admin`, contraseña `GRAFANA_ADMIN_PASSWORD`). El datasource **EcoNest** ya viene configurado, con un usuario de solo lectura.

> El script `docker/init-db.sh` solo se ejecuta al crear el volumen de Postgres por primera vez. Si cambias `GRAFANA_DB_PASSWORD` después, haz `docker compose down -v` (borra los datos).

## Límites y arranque seguro

- **`ADMIN_TOKEN` es obligatorio**: la API no arranca si falta, tiene menos de 16 caracteres o es un valor típico (`change-me`, `admin`...). `docker compose` tampoco arranca si falta cualquier secreto de `.env`. Genera valores con `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- **Tamaño de las peticiones** (configurable por entorno):

| Variable | Por defecto | Efecto |
|---|---|---|
| `MAX_SCREENSHOT_BYTES` | 2 000 000 | Tamaño máximo de la captura ya decodificada |
| `MAX_DETECTIONS_PER_EVENT` | 100 | Máximo de detecciones en un solo `POST /detections` (422) |
| — (derivado) | ≈ 2,8 MB | Cuerpo máximo de cualquier POST/PUT/PATCH: si `Content-Length` lo supera, 413 antes de leer nada |

- Las peticiones con cuerpo deben llevar `Content-Length`; con `Transfer-Encoding: chunked` y sin longitud se responde 411. Los clientes habituales (`httpx`, `requests`, `curl -d`) ya lo envían.
- Pendiente: poner un proxy inverso con HTTPS delante (Caddy/nginx) con su propio límite de cuerpo.

## CORS y estado de los dispositivos

- **CORS:** los navegadores solo pueden llamar a la API desde los orígenes de `CORS_ORIGINS` (por defecto `http://localhost:5173,http://localhost:3000`). En producción pon el dominio real del frontend, separado por comas; `*` permite cualquiera. No se usan cookies: el token va en la cabecera `Authorization`.
- **Online/offline:** un dispositivo está `online` si su último heartbeat (`POST /devices/me/status`) tiene menos de `ONLINE_THRESHOLD_SECONDS` (180 por defecto). La Raspberry debe enviarlo cada ~60 s. Las métricas se guardan en la tabla `device_status`, que Grafana puede graficar directamente.
- El histórico de `device_status` crece sin límite (≈1 440 filas/día por dispositivo con un heartbeat por minuto); conviene una política de retención más adelante.

## Registrar un dispositivo (una vez por Raspberry)

```bash
curl -X POST localhost:8000/devices \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"id":"nest-01","name":"Farola 1","zone":"Doña Casilda","lat":43.263,"lon":-2.935}'
# → {"id":"nest-01","token":"..."}   ← el token solo se muestra ahora; guardadlo en la Raspberry
```

## Enviar una detección (lo que hará el cliente de la Raspberry)

```bash
curl -X POST localhost:8000/detections \
  -H "Authorization: Bearer $DEVICE_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "device_id": "nest-01",
    "timestamp": "2026-11-12T10:15:00Z",
    "location": {"lat": 43.263, "lon": -2.935, "zone": "Doña Casilda"},
    "detections": [{"class": "pigeon", "confidence": 0.91, "bbox": [120, 80, 64, 48]}],
    "count": 1,
    "screenshot": "<JPEG o PNG en base64, opcional, máx. 2 MB>"
  }'
```

## Endpoints

| Método | Ruta | Auth | Uso |
|---|---|---|---|
| POST | `/devices` | admin | Registrar un dispositivo y obtener su token |
| POST | `/detections` | dispositivo | Enviar una detección |
| POST | `/devices/me/status` | dispositivo | Heartbeat con métricas de la Raspberry (`cpu_temp_c`, `load_1m`, `mem_used_pct`, `disk_used_pct`, `uptime_s`; todas opcionales). La hora la pone el servidor |
| GET | `/devices` | pública | Dispositivos con `online`, `last_seen` y últimas métricas |
| GET | `/devices/{id}/status` | pública | Histórico de métricas, más reciente primero (`since`, `until`, `limit`) |
| GET | `/detections` | pública | Historial. Filtros: `zone`, `device_id`, `since`, `until`, `limit`, `offset` |
| GET | `/counts` | pública | Total de palomas por zona y hora/día (`granularity=hour\|day`) |
| GET | `/heatmap` | pública | Puntos `lat, lon, weight` agregados en celdas (`precision` = decimales). Filtros: `zone`, `since`, `until` |
| GET | `/screenshots/{id}` | pública | Captura de una detección |
| GET | `/health` | pública | Comprobación de estado |

Las lecturas son públicas porque el informe plantea que los datos estén abiertos a la ciudadanía. Si se decide lo contrario, basta con añadir una dependencia de autenticación a esas rutas.

## Tests

```bash
pip install -r requirements.txt
pytest
```

Los tests usan SQLite por defecto. Para ejecutarlos contra Postgres: `DATABASE_URL=postgresql+psycopg://... pytest`
(hay que definirla antes de importar `app`, como hace la cabecera de `tests/test_api.py`).

## Pendiente / decisiones abiertas

- **Privacidad de las capturas:** el informe dice "solo aves", pero una cámara en un parque puede captar personas. Lo razonable es que la Raspberry **descarte o difumine** cualquier captura donde YOLO detecte `person` *antes* de enviarla. La API solo valida que sea una imagen válida y de tamaño razonable.
- **Migraciones:** ahora las tablas se crean al arrancar (`create_all`). Si el esquema cambia, habría que pasar a Alembic.
- **Capturas en disco:** valen para el MVP. Más adelante, un bucket (S3/MinIO) y una política de borrado.
- **HTTPS:** la API habla HTTP plano; el informe exige HTTPS, así que hay que ponerle delante un proxy inverso (Caddy o nginx) con certificado.
- **Dashboards de Grafana:** el datasource está listo, pero los paneles (conteo, mapa de calor, historial, capturas) están por crear.
