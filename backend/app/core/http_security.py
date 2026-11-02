"""Limita corpos sensíveis e evita respostas de erro com dados internos."""

from starlette.responses import JSONResponse


class ProtectedApiBoundary:
    """Aplica limites e no-store a autenticação e organizações, inclusive nos erros."""

    def __init__(self, app, *, api_prefix: str) -> None:
        self.app = app
        self.prefix = api_prefix

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        protected = any(path == self.prefix + segment or path.startswith(self.prefix + segment + "/")
                        for segment in ("/auth", "/organizations"))
        if scope["type"] != "http" or not protected:
            await self.app(scope, receive, send)
            return
        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = [(key, value) for key, value in message.get("headers", [])
                           if key.lower() not in (b"cache-control", b"pragma")]
                message = {**message, "headers": headers + [(b"cache-control", b"no-store"), (b"pragma", b"no-cache")]}
            await send(message)

        # Todas as escritas de organização e os corpos de credenciais são limitados.
        bounded_path = path.startswith(self.prefix + "/organizations") or path.rstrip("/") in (
            self.prefix + "/auth/login", self.prefix + "/auth/invitations/accept",
        )
        if bounded_path and scope.get("method") in ("POST", "PUT", "PATCH"):
            content_type = dict(scope.get("headers", [])).get(b"content-type", b"").split(b";", 1)[0].strip().lower()
            if content_type != b"application/json":
                await JSONResponse({"detail": "Envie dados no formato JSON."}, 415)(scope, receive, secure_send)
                return
            chunks, size = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > 4096:
                    await JSONResponse({"detail": "Requisição excede o limite permitido."}, 413)(scope, receive, secure_send)
                    return
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                return await receive()

            downstream_receive = bounded_receive
        else:
            downstream_receive = receive
        await self.app(scope, downstream_receive, secure_send)
