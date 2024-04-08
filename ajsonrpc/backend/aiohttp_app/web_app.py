import asyncio
from typing import Any, Callable, Coroutine, Optional, Type, Union
from functools import partial, update_wrapper
try:
    from ssl import SSLContext
except ImportError:  # pragma: no cover
    SSLContext = Any  # type: ignore
try:
    import ujson as json
except Exception:
    import json
from marshmallow import Schema
from aiohttp.hdrs import METH_OPTIONS
from aiohttp.abc import AbstractView, AbstractMatchInfo
from aiohttp.web_response import StreamResponse
from aiohttp.web_exceptions import HTTPUnauthorized, HTTPInternalServerError, HTTPBadRequest
from aiohttp.web import Application as AiohttpApplication
from aiohttp.web_request import Request
from aiohttp.typedefs import Handler
from aiohttp.web_urldispatcher import AbstractRoute, _ExpectHandler
from aiohttp import hdrs

from .utils import calc_request_get_params
from .base import set_auth_header_name, get_auth_header_name

import logging
logger = logging.getLogger()


WAIT_TASKS = ('Totalizer.run')


# advanced web-Application
class Application(AiohttpApplication):
    def __init__(self,
                 auth_header_name: str = None,
                 auth_base_paths: list = None,
                 auth_getter_data: Callable[[str], dict] or Coroutine[str] = None,
                 *args, **kwargs):
        super(Application, self).__init__(*args, **kwargs)

        # for authentication
        # set header-name for getting auth token
        set_auth_header_name(self, auth_header_name)
        # method for getting token-data by token
        self.auth_data_getter = auth_getter_data
        # for check path.startswith
        self.auth_base_paths = tuple(auth_base_paths or [])

        # marshmallow schemas for handlers
        self._handle_schemas = {}

    # alias for add route to url-dispatcher with marshmallow schemas and added options method
    def add_route(
        self,
        method: str,
        path: str,
        handler: Union[Handler, Type[AbstractView]],
        *,
        name: Optional[str] = None,
        expect_handler: Optional[_ExpectHandler] = None,
        schema: Schema = None,
        options_method: bool = True
    ) -> AbstractRoute:
        # add route
        resource = self.router.add_resource(path, name=name)
        route = resource.add_route(method, handler, expect_handler=expect_handler)
        if route:
            # add options method
            if options_method:
                # TODO error if method has ben added
                try:
                    resource.add_route(METH_OPTIONS, handler, expect_handler=expect_handler)
                except Exception as e:
                    logger.warning(f'{self.__class__.__name__}::add_route: msg=fail added options method, {e=}')
            # save schema
            if schema:
                self._handle_schemas.setdefault(path, {})
                self._handle_schemas[path][method] = schema
        return route

    # request handler
    # add: authorization check
    # add: get-parameter validation by marshmallow schemas (see self.add_route)
    async def _handle(self, request: Request) -> StreamResponse:
        logger_prefix = f'{self.__class__.__name__}::_handle'
        loop = asyncio.get_event_loop()
        debug = loop.get_debug()
        match_info = await self._router.resolve(request)
        if debug:  # pragma: no cover
            if not isinstance(match_info, AbstractMatchInfo):
                raise TypeError(
                    "match_info should be AbstractMatchInfo "
                    "instance, not {!r}".format(match_info)
                )
        match_info.add_app(self)

        match_info.freeze()

        resp = None
        request._match_info = match_info
        expect = request.headers.get(hdrs.EXPECT)
        if expect:
            resp = await match_info.expect_handler(request)
            await request.writer.drain()

        handler = match_info.handler
        canonical = match_info.route.resource.canonical if match_info.route.resource else None

        # -- check access to method by header
        if resp is None:
            if canonical and request.method != METH_OPTIONS:
                # check access, get token-data and added to request
                for base_path in self.auth_base_paths:
                    if canonical.startswith(base_path):
                        access = False
                        # token_key = 'WMyBO4aUUMfv4N0z5iAl1lEKLNZpigK4S8tv0tfI4i2YVSlQ1JZQUsqu3dJbhj30'
                        # if token_key:
                        if token_key := request.headers.get(get_auth_header_name(self)):
                            try:
                                auth_data = self.auth_data_getter(request, token_key)
                            except Exception as e:
                                logger.error(f'{logger_prefix}: msg=fail execute auth_data_getter, {e=}')
                                # resp = HTTPInternalServerError(reason='Fail authorization')
                                resp = HTTPInternalServerError()
                            else:
                                if asyncio.iscoroutine(auth_data):
                                    auth_data = await auth_data

                                if auth_data:
                                    access = True
                                    request['extra_data'] = auth_data
                        if not access:
                            resp = HTTPUnauthorized()

        # -- validate get-params
        if resp is None:
            try:
                schema_cls = self._handle_schemas[canonical][request.method]
            except Exception as e:
                pass
            else:
                request['params'], errors = calc_request_get_params(schema_cls(), request)
                if errors:
                    resp = HTTPBadRequest(body=json.dumps(dict(errors=errors)), content_type='application/json')

        # -- go to method logic
        if resp is None:
            if self._run_middlewares:
                for app in match_info.apps[::-1]:
                    for m, new_style in app._middlewares_handlers:  # type: ignore[union-attr] # noqa
                        if new_style:
                            handler = update_wrapper(
                                partial(m, handler=handler), handler
                            )
                        else:
                            handler = await m(app, handler)  # type: ignore[arg-type]

            resp = await handler(request)

        return resp
