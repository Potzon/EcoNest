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
| GET | `/detections` | pública | Historial. Filtros: `zone`, `device_id`, `since`, `until`, `limit`, `offset` |
| GET | `/counts` | pública | Total de palomas por zona y hora/día (`granularity=hour\|day`) |
| GET | `/heatmap` | pública | Puntos `lat, lon, weight` agregados en celdas (`precision` = decimales) |
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
