try:
    import ujson as json
except Exception:
    import json
from typing import Callable
from time import time
from dataclasses import dataclass

from aiohttp.hdrs import METH_POST, METH_GET
from aiohttp.web import json_response, Request

from ...core import JSONRPC20Response
from ...dispatcher import Dispatcher
from ...swagger_gen import generate_swagger_info
from ..aiohttp import JSONRPCAiohttp
from .web_app import Application

import logging
logger = logging.getLogger()


# storage is for saved swaggers jsons
SWAGGER_CFGS = {}


def swagger_handler(request):
    data = SWAGGER_CFGS[request.path].copy()
    hosts = [f'https://{request.host}', f'http://{request.host}']
    data['servers'] = [dict(url=addr) for addr in hosts]
    return json_response(
        data=data,
        dumps=json.dumps,
    )


def add_jsonrpc_json_handler(web_app: Application, api_path: str, dispatcher: Dispatcher):
    async def _handler(request):
        methods = {}
        for m in dispatcher.values():
            s = m.name.split('.')

            """!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
            !!!   not change the data format  !!!
            !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"""
            m_name = '_'.join(s[1:len(s)])
            dir_name = s[0]
            methods.setdefault(dir_name, {})
            if m_name in methods[dir_name]:
                logger.error(f'add_jsonrpc_json_handler: msg=method is duplicated, method_name={m.name}')
            methods[dir_name][m_name] = m.name

        return json_response(data=methods)

    return web_app.router.add_route(METH_GET,  f'{api_path}/jsonrpc/2.0/json', _handler)


@dataclass
# config for jsonrpc api
class ApiCfg:
    title: str
    path: str
    methods: list
    auth_callback: Callable = None
    finish_callback: Callable = None
    # add route for getting json with all methods
    api_json: bool = True
    # add route for getting json-config for swagger
    swagger: bool = True


def install_jsonrpc2_apis(web_app: Application, apis: [ApiCfg]) -> list:
    result = []

    for api_cfg in apis:    # type: ApiCfg
        # create jsonrpc api
        api = JSONRPCAiohttp(auth_callback=api_cfg.auth_callback, finish_callback=api_cfg.finish_callback)
        [api.manager.dispatcher.add_class_method(**method_data) for method_data in api_cfg.methods]

        # register jsonrpc in web-application
        web_app.router.add_route(METH_POST,     api_cfg.path,       api.handler)

        # add handler for getting all methods (json)
        if api_cfg.api_json:
            add_jsonrpc_json_handler(web_app=web_app, api_path=api_cfg.path, dispatcher=api.manager.dispatcher)

        # add handler for getting swagger config
        if api_cfg.swagger:
            path = f'/docs{api_cfg.path}/json'
            SWAGGER_CFGS[path] = generate_swagger_info(
                routes=api.manager.dispatcher.values(),
                path=api_cfg.path,
                description='',
                api_version='0.1.0',
                auth_header_name='X-AccessToken',
                title=api_cfg.title,
                hosts=[],
            )

            web_app.router.add_route(
                METH_GET,
                path,
                swagger_handler
            )

        result.append(api)

    return result
