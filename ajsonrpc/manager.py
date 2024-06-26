import copy
import json
import inspect
import asyncio
from typing import Optional, Union, Iterable, Mapping

from .core import (
    JSONRPC20Request, JSONRPC20BatchRequest, JSONRPC20Response,
    JSONRPC20BatchResponse, JSONRPC20MethodNotFound, JSONRPC20InvalidParams,
    JSONRPC20ServerError, JSONRPC20ParseError, JSONRPC20InvalidRequest,
    JSONRPC20DispatchException, JSONRPC20InvalidParamsException,
    JSONRPC20InvalidResultException,
)
from .dispatcher import Dispatcher, MethodSettings
from .utils import is_invalid_params, validate_by_schema

import logging
logger = logging.getLogger()


class AsyncJSONRPCResponseManager:

    """Async JSON-RPC Response manager."""

    def __init__(self, dispatcher: Dispatcher, serialize=json.dumps, deserialize=json.loads):
        self.dispatcher = dispatcher
        self.serialize = serialize
        self.deserialize = deserialize

    async def get_response_for_request(self, request: JSONRPC20Request) -> Optional[JSONRPC20Response]:
        """Get response for an individual request."""
        output = None
        response_id = request.id or None
        log_prefix = f'{__name__}::get_response_for_request'
        try:
            method = self.dispatcher[request.method]
        except KeyError:
            # method not found
            output = JSONRPC20Response(
                error=JSONRPC20MethodNotFound(),
                id=response_id
            )
        else:
            try:
                # controller - class with method
                if isinstance(method, MethodSettings):
                    method_settings = method
                    # deprecated log
                    if method.deprecated:
                        logger.warning(f'{log_prefix}: msg=method is deprecated, name={method.name}, func_name={method.func_name}')

                    # check ACL
                    if method.acl or method.acl_func:
                        # { module_name: allowed_acl_value, }
                        if user_acl := request.extra_data.get('user_acl'):
                            if method.acl_func:
                                if not method.acl_func(user_acl):
                                    raise PermissionError('Method is forbidden')
                            else:
                                for module_name in user_acl:
                                    if module_name in method.acl:
                                        if user_acl[module_name] & method.acl[module_name] == method.acl[module_name]:
                                            break
                                        else:
                                            raise PermissionError('Method is forbidden')
                                else:
                                    raise PermissionError('Method is forbidden')


                    # validate params
                    if method.schema:
                        validation_errors = request.validate_params(method.schema)
                        if validation_errors:
                            raise JSONRPC20InvalidParamsException(data=validation_errors)

                    # run methods
                    obj = method.cls(request)
                    method = getattr(obj, method.func_name)
                    result, error = await method() \
                        if inspect.iscoroutinefunction(method) \
                        else method()   # type: JSONRPC20Response

                    # validate result
                    if result and method_settings.response_schema:
                        if isinstance(result, list):
                            v_result = []
                            for res_item in result:
                                v_res_item, validation_errors = validate_by_schema(method_settings.response_schema, res_item)
                                if validation_errors:
                                    raise JSONRPC20InvalidResultException(data=validation_errors, invalid_data=res_item, method=method_settings.name)
                                v_result.append(v_res_item)
                            else:
                                result = v_result
                        else:
                            result, validation_errors = validate_by_schema(method_settings.response_schema, result)
                            if validation_errors:
                                raise JSONRPC20InvalidResultException(data=validation_errors, invalid_data=result, method=method_settings.name)

                # controller - function or object with method
                else:
                    result, error = await method(request) \
                        if inspect.iscoroutinefunction(method) \
                        else method(request)    # type: JSONRPC20Response

            except JSONRPC20InvalidParamsException as dispatch_error:
                output = JSONRPC20Response(
                    error=dispatch_error.error,
                    id=response_id
                )

            except JSONRPC20InvalidResultException as e:
                logger.error(f'{log_prefix}: msg=result is not valid by response schema, method={e.method}', exc_info=e, extra=dict(
                    method=method,
                    method_name=e.method,
                    error=e.error.data,
                    invalid_data=e.invalid_data,
                ))
                output = JSONRPC20Response(
                    error=JSONRPC20ServerError(),
                    id=response_id
                )

            except JSONRPC20DispatchException as dispatch_error:
                # Dispatcher method raised exception with controlled "data"
                output = JSONRPC20Response(
                    error=dispatch_error.error,
                    id=response_id
                )

            except PermissionError as e:
                output = JSONRPC20Response(
                    error=JSONRPC20InvalidRequest(
                        data=[{
                            "selector": 'permission',
                            "value": e.__class__.__name__,
                            "reason": str(e),
                        }]
                    ),
                    id=response_id
                )
                logger.error(
                    f'{log_prefix}: name={request.method}, msg={type(e)}, output={output.__class__.__name__}, {response_id=}',
                    exc_info=e,
                    extra=dict(
                        extra_data=request.extra_data
                    ))

            except Exception as e:
                # TODO: fix check is_invalid_params
                if 1 == 2 and is_invalid_params(method, *request.args, **request.kwargs):
                    # Method's parameters are incorrect
                    output = JSONRPC20Response(
                        error=JSONRPC20InvalidParams(),
                        id=response_id
                    )
                else:
                    # Dispatcher method raised exception
                    output = JSONRPC20Response(
                        error=JSONRPC20ServerError(
                            data=[{
                                "selector": e.__class__.__name__,
                                "reason": str(e),
                            }]
                        ),
                        id=response_id
                    )
                logger.error(
                    f'{log_prefix}: name={request.method}, msg={type(e)}, output={output.__class__.__name__}, {response_id=}',
                    exc_info=e,
                    extra=dict(
                        extra_data=request.extra_data
                    ))

            else:
                output = JSONRPC20Response(result=result, error=error, id=response_id)

        # -- result log
        res_txt = ''
        if output.result:
            res_txt = 'SUCCESS'
        if output.error:
            res_txt = f'ERROR [{output.error.code}, {output.error.message}, {output.error.data}]'
        logger.info(f'{log_prefix}: msg={res_txt}, name={request.method}, output={output.__class__.__name__}, '
                    f'id={id(request)}, http_id={request.extra_data.get("_id")}, ip={request.extra_data.get("_ip")}, '
                    f'cid={request.extra_data.get("cid")}, token_id={request.extra_data.get("token_id")}, {response_id}')

        output.request = request

        return output

    async def get_response_for_request_body(self, request_body, extra_data: dict = None) -> Optional[JSONRPC20Response]:
        """Catch parse error as well"""
        try:
            request = JSONRPC20Request.from_body(request_body)
            request.extra_data = extra_data
        except ValueError as e:
            return JSONRPC20Response(error=JSONRPC20InvalidRequest(data=dict(reason=str(e))))
        else:
            return await self.get_response_for_request(request)

    async def get_response_for_payload(self, payload: str, extra_data: dict = None, finish_callback = None)\
            -> Optional[Union[JSONRPC20Response, JSONRPC20BatchResponse]]:
        """Top level handler

        NOTE: top level handler, accepts string payload.

        """
        try:
            request_data = self.deserialize(payload)
        except (TypeError, ValueError):
            return JSONRPC20Response(error=JSONRPC20ParseError())

        # check if iterable, and determine what request to instantiate.
        is_batch_request = isinstance(request_data, Iterable) \
            and not isinstance(request_data, Mapping)
        if is_batch_request and len(request_data) == 0:
            return JSONRPC20Response(error=JSONRPC20InvalidRequest())

        requests_bodies = request_data if is_batch_request else [request_data]

        responses = await asyncio.gather(*[
            self.get_response_for_request_body(request_body, extra_data=copy.copy(extra_data))
            for request_body in requests_bodies
        ])

        # nonempty_responses = [r for r in responses if r is not None]
        nonempty_responses = []
        for r in responses: # type: JSONRPC20Response
            if not r.request or not r.request.is_notification:
                nonempty_responses.append(r)

        # run finish callback, example - logger
        if finish_callback:
            try:
                if inspect.iscoroutinefunction(finish_callback):
                    asyncio.ensure_future(finish_callback(responses))
                else:
                    finish_callback(responses)
            except Exception as e:
                logger.error(f'{__name__}::get_response_for_payload: msg=fail running finish_callback {e=}', exc_info=e)

        if is_batch_request:
            if len(nonempty_responses) > 0:
                return JSONRPC20BatchResponse(nonempty_responses)
        elif len(nonempty_responses) > 0:
            return nonempty_responses[0]

    async def get_payload_for_payload(self, payload: str) -> str:
        response = await self.get_response_for_payload(payload)

        if response is None:
            return ""

        return self.serialize(response.body)
