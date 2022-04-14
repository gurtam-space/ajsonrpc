from ajsonrpc.core import JSONRPC20Request


# jsonrpc2 base controller
class BaseJSONRPC20Controller:
    def __init__(self, request: JSONRPC20Request, *args, **kwargs):
        self._request = request

    @property
    def request(self) -> JSONRPC20Request:
        return self._request
