import inspect
try:
    import ujson as json
except Exception:
    import json
from aiohttp.web import Request, Response

from .common import CommonBackend


class JSONRPCAiohttp(CommonBackend):
    def __init__(self, auth_callback=None, **kwargs):
        super().__init__(**kwargs)
        # return (int - response.status value, dict - auth_data for handlers)
        # if status != 200 - return empty response with status !200
        self.auth_callback = auth_callback

    @property
    def handler(self):
        async def _handler(request: Request):
            # -- check auth
            if self.auth_callback:
                auth_result = await self.auth_callback(request) \
                    if inspect.iscoroutinefunction(self.auth_callback) \
                    else self.auth_callback(request)
                resp_status = int(auth_result[0])
                extra_data = dict(auth_result[1])
            else:
                resp_status = 200
                extra_data = dict()

            # -- go to json-rpc methods
            if resp_status == 200:
                txt = await request.text()
                rpc_resp = await self.manager.get_response_for_payload(txt, extra_data)
                resp = Response(body=json.dumps(rpc_resp.body), content_type="application/json")
            else:
                resp = Response(status=resp_status)

            # body_str = await manager.get_payload_for_payload(txt)
            # return Response(body=body_str, content_type="application/json")
            return resp

        return _handler
