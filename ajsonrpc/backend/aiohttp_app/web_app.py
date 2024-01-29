import sys
import asyncio
import socket
from typing import Any, Awaitable, Callable, Coroutine, Optional, Type, Union, Iterable
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
from aiohttp.abc import AbstractAccessLogger, AbstractView, AbstractMatchInfo
from aiohttp.web_response import StreamResponse
from aiohttp.web_exceptions import HTTPUnauthorized, HTTPInternalServerError, HTTPBadRequest
from aiohttp.web_log import AccessLogger
from aiohttp.log import access_logger
from aiohttp.web_runner import GracefulExit
from aiohttp.web import Application as AiohttpApplication, _run_app
from aiohttp.web_request import Request
from aiohttp.typedefs import Handler
from aiohttp.web_urldispatcher import AbstractRoute, _ExpectHandler
from aiohttp import hdrs

from .utils import calc_request_get_params
from .base import set_auth_header_name, get_auth_header_name

import logging
logger = logging.getLogger()

# task list to cancel
CANCEL_TASKS_DEF = '_run_app', 'MQTTProtocol._read_loop', 'Client._resend_qos_messages', 'ClickhouseDB.run_wait',


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

    # def add_routes(self, routes: Iterable[AbstractRouteDef]) -> List[AbstractRoute]: pass

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


# callback stop tasks
def _cancel_all_tasks(loop: asyncio.AbstractEventLoop, on_stop: list, cancel_tasks: list, timeout) -> None:
    # run stop callbacks
    for f in on_stop:
        if asyncio.iscoroutinefunction(f):
            asyncio.ensure_future(f())
        else:
            f()

    # waiting for tasks not from the list of canceled
    to_wait = asyncio.all_tasks(loop)
    if not to_wait:
        return
    for task in list(to_wait):
        for name in cancel_tasks:
            if task._coro.__qualname__ != name:
                continue
            to_wait.remove(task)
    if to_wait:
        loop.run_until_complete(asyncio.wait(to_wait, timeout=timeout))

    # cancel all tasks
    to_cancel = asyncio.all_tasks(loop)
    if not to_cancel:
        return
    for task in to_cancel:
        task.cancel()
    loop.run_until_complete(
        asyncio.gather(*to_cancel, return_exceptions=True))

    for task in to_cancel:
        if task.cancelled():
            continue
        if task.exception() is not None:
            loop.call_exception_handler({
                'message': 'unhandled exception during asyncio.run() shutdown',
                'exception': task.exception(),
                'task': task,
            })


# start application coro
def run_app(app: Union[Application, Awaitable[Application]], *,
            host: Optional[str]=None,
            port: Optional[int]=None,
            path: Optional[str]=None,
            sock: Optional[socket.socket]=None,
            shutdown_timeout: float=60.0,
            ssl_context: Optional[SSLContext]=None,
            print: Callable[..., None]=print,
            backlog: int=128,
            access_log_class: Type[AbstractAccessLogger]=AccessLogger,
            access_log_format: str=AccessLogger.LOG_FORMAT,
            access_log: Optional[logging.Logger]=access_logger,
            handle_signals: bool=True,
            reuse_address: Optional[bool]=None,
            reuse_port: Optional[bool]=None,
            on_stop: Optional[list]=[],
            cancel_tasks: Optional[list]=[]) -> None:
    """Run an app locally"""
    loop = asyncio.get_event_loop()

    # Configure if and only if in debugging mode and using the default logger
    if loop.get_debug() and access_log and access_log.name == 'aiohttp.access':
        if access_log.level == logging.NOTSET:
            access_log.setLevel(logging.DEBUG)
        if not access_log.hasHandlers():
            access_log.addHandler(logging.StreamHandler())

    try:
        loop.run_until_complete(_run_app(app,
                                host=host,
                                port=port,
                                path=path,
                                sock=sock,
                                shutdown_timeout=shutdown_timeout,
                                ssl_context=ssl_context,
                                print=print,
                                backlog=backlog,
                                access_log_class=access_log_class,
                                access_log_format=access_log_format,
                                access_log=access_log,
                                handle_signals=handle_signals,
                                reuse_address=reuse_address,
                                reuse_port=reuse_port))
    except (GracefulExit, KeyboardInterrupt):  # pragma: no cover
        pass
    finally:
        cancel_tasks.extend(CANCEL_TASKS_DEF)
        _cancel_all_tasks(loop, on_stop, cancel_tasks, shutdown_timeout)
        if sys.version_info >= (3, 6):  # don't use PY_36 to pass mypy
            loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
