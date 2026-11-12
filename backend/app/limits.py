"""Límite del tamaño del cuerpo de las peticiones.

Sin esto, FastAPI lee y parsea el JSON completo ANTES de que ninguna validación
pueda rechazarlo. Aquí se decide mirando solo las cabeceras:

- Content-Length mayor que el máximo  -> 413
- Transfer-Encoding sin Content-Length (chunked, tamaño desconocido) -> 411

Con Content-Length obligatorio el servidor HTTP lee exactamente esa cantidad de
bytes, así que el tope es real. Un proxy inverso (Caddy/nginx) debería aplicar
además su propio límite delante.
"""
from starlette.responses import JSONResponse

_WITH_BODY = {"POST", "PUT", "PATCH"}


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in _WITH_BODY:
            headers = dict(scope["headers"])
            length = headers.get(b"content-length")
            if length is None:
                if b"transfer-encoding" in headers:
                    return await self._reject(411, "Content-Length required", scope, receive, send)
            elif not length.isdigit():
                return await self._reject(400, "Invalid Content-Length", scope, receive, send)
            elif int(length) > self.max_bytes:
                return await self._reject(413, f"Request body too large (max {self.max_bytes} bytes)", scope, receive, send)
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(status, detail, scope, receive, send):
        await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
