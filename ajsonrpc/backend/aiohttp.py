import json
from aiohttp.web import Request, Response

from .common import CommonBackend


class JSONRPCAiohttp(CommonBackend):
    @property
    def handler(self):
        async def _handler(request: Request):
            txt = await request.text()
            response = await self.manager.get_response_for_payload(txt)
            return Response(body=json.dumps(response.body), content_type="application/json")
            # body_str = await manager.get_payload_for_payload(txt)
            # return Response(body=body_str, content_type="application/json")

        return _handler
