import ujson
from aiohttp import web
from aiohttp.hdrs import METH_GET, METH_POST, METH_PUT, METH_DELETE
from aiohttp.web_urldispatcher import View
from marshmallow import UnmarshalResult, Schema, fields

import logging
logger = logging.getLogger()


class BaseHttpController(View):
    """
    aiohttp base controller
    """
    # def __init__(self, request: [web.Request]):
    #     super().__init__(request)

    @property
    # get-params from request getter
    def request_get_params(self) -> dict:
        logger.warning(f'{self.__class__.__name__}::request_get_params: msg=method is deprecated - use request.get("extra_data")')
        return self.request.get('extra_data')

    # handler for OPTIONS http-method
    async def options(self):
        return web.json_response(status=200)
