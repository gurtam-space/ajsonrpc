"""
    base application for jsonrpc2 api with aiohttp

    marshmallow==2.20.* is required library
"""
from .web_app import Application, WAIT_TASKS
from .aiohttp_controller import BaseHttpController
from .jsonrpc2_controller import BaseJSONRPC20Controller
from .jsonrpc2_model import BaseJSONRPC20Model
from .jsonrpc2_installer import ApiCfg, install_jsonrpc2_apis

# __all__ = [
#     'Application', 'run_app',
#     'BaseHttpController',
#     'BaseJSONRPC20Controller',
#     'JSONRPCAiohttp',
# ]
