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
)
from .dispatcher import Dispatcher
from .utils import is_invalid_params


class AsyncJSONRPCResponseManager:

    """Async JSON-RPC Response manager."""

    def __init__(self, dispatcher: Dispatcher, serialize=json.dumps, deserialize=json.loads, is_server_error_verbose=False):
        self.dispatcher = dispatcher
        self.serialize = serialize
        self.deserialize = deserialize
        self.is_server_error_verbose = is_server_error_verbose

    async def get_response_for_request(self, request: JSONRPC20Request) -> Optional[JSONRPC20Response]:
        """Get response for an individual request."""
        output = None
        response_id = request.id if not request.is_notification else None
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
                if isinstance(method, dict):
                    # validate params
                    schema = method.get('schema')
                    if schema:
                        validation_errors = request.validate_params(schema)
                        if validation_errors:
                            raise JSONRPC20InvalidParamsException(data=validation_errors)
                    # run methods
                    obj = method['cls'](request)
                    method = getattr(obj, method['func_name'])
                    result, error = await method() \
                        if inspect.iscoroutinefunction(method) \
                        else method()   # type: JSONRPC20Response
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

            except JSONRPC20DispatchException as dispatch_error:
                # Dispatcher method raised exception with controlled "data"
                output = JSONRPC20Response(
                    error=dispatch_error.error,
                    id=response_id
                )

            except Exception as e:
                raise e
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
                                "value": e.args,
                                "reason": str(e),
                            }] if self.is_server_error_verbose else None
                        ),
                        id=response_id
                    )
            else:
                output = JSONRPC20Response(result=result, error=error, id=response_id)

        if not request.is_notification:
            return output

    async def get_response_for_request_body(self, request_body, extra_data: dict = None) -> Optional[JSONRPC20Response]:
        """Catch parse error as well"""
        try:
            request = JSONRPC20Request.from_body(request_body)
            request.extra_data = extra_data
        except ValueError:
            return JSONRPC20Response(error=JSONRPC20InvalidRequest())
        else:
            return await self.get_response_for_request(request)

    async def get_response_for_payload(self, payload: str, extra_data: dict = None) -> Optional[Union[JSONRPC20Response, JSONRPC20BatchResponse]]:
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
        nonempty_responses = [r for r in responses if r is not None]
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
