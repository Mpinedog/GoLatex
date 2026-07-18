"""Bus de eventos: difunde a los WebSockets de la UI, con debounce por clave."""
import asyncio
import json
import logging

log = logging.getLogger("golatex.events")


class EventBus:
    def __init__(self):
        self.clients: set = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self._debounce: dict[str, asyncio.TimerHandle] = {}

    def attach_loop(self):
        self.loop = asyncio.get_running_loop()

    async def connect(self, ws):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws):
        self.clients.discard(ws)

    def broadcast(self, event: dict) -> None:
        """Difunde un evento a todos los clientes (desde el loop principal)."""
        if not self.loop:
            return
        data = json.dumps(event, ensure_ascii=False)
        for ws in list(self.clients):
            asyncio.ensure_future(self._send(ws, data), loop=self.loop)

    async def _send(self, ws, data: str):
        try:
            await ws.send_text(data)
        except Exception:
            self.disconnect(ws)

    def broadcast_threadsafe(self, event: dict) -> None:
        """Versión segura para llamar desde hilos (watchdog)."""
        if self.loop:
            self.loop.call_soon_threadsafe(self.broadcast, event)

    def broadcast_debounced(self, key: str, delay: float, make_event) -> None:
        """Programa un broadcast tras `delay` s; llamadas repetidas con la misma
        clave reinician el temporizador. `make_event` se evalúa al disparar.
        Seguro para llamar desde hilos."""
        if not self.loop:
            return

        def schedule():
            prev = self._debounce.pop(key, None)
            if prev:
                prev.cancel()

            def fire():
                self._debounce.pop(key, None)
                try:
                    self.broadcast(make_event())
                except Exception:
                    log.exception("evento debounced falló (%s)", key)

            self._debounce[key] = self.loop.call_later(delay, fire)

        self.loop.call_soon_threadsafe(schedule)
