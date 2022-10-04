import aiohttp.web_request
from aiohttp.web_request import Request
try:
    from spaceapi import SpaceApiClient
except Exception:
    SpaceApiClient = None

from .base import get_auth_header_name

import logging
logger = logging.getLogger()


# access levels - for select entity-fields
class ACCESS_LVL:
    FLEET = 10
    TSP = 20
    SPACE = 30


# get fleet data
async def get_fleet_data(cid: str) -> dict:
    assert SpaceApiClient
    data, errs = await SpaceApiClient().sun_state.one_request(
        SpaceApiClient().sun_state.methods.dstate['search_by_key'],
        dict(
            entity='fleet',
            key=cid,
            fields=['id', 'access_lvl']
        )
    )
    if errs:
        logger.error(f'{__name__}::get_fleet_data: msg=fail getting, {cid=}, {errs=}')

    return dict(
        id=data['id'],
        access_lvl=data['access_lvl'],
    ) if data else {}


# get tsp data
async def get_tsp_data(cid: str) -> dict:
    assert SpaceApiClient
    data, errs = await SpaceApiClient().sun_state.one_request(
        SpaceApiClient().sun_state.methods.dstate['search_by_key'],
        dict(
            entity='tsp',
            key=cid,
            fields=['id', 'access_lvl']
        )
    )
    if errs:
        logger.error(f'{__name__}::get_tsp_data: msg=fail getting, {cid=}, {errs=}')

    return dict(
        id=data['id'],
        access_lvl=data['access_lvl'],
    ) if data else {}


# get auth data by token.key
async def get_token_data(key: str) -> dict:
    assert SpaceApiClient
    token_data, errs = await SpaceApiClient().sun_state.one_request(
        SpaceApiClient().sun_state.methods.dstate['search'],
        dict(
            entity='token',
            c=[['key', key, 'eq']],
            count=1,
            fields=['id', 'cid', 'access_lvl', 'info', 'subscription', 'subscriptions', 'store', 'country', 'td']
        )
    )
    if errs:
        logger.error(f'get_token_data: msg=fail getting token, {key=}, {errs=}')

    return dict(
        cid=token_data['cid'],
        token_id=token_data['id'],
        access_lvl=token_data['access_lvl'],
        app_id=token_data['info'].get('app_id') or None,
        # deprecated field
        subscription_id=subscription.get('subscription_id') or None if (subscription := token_data.get('subscription')) else None,
        subscriptions=token_data.get('subscriptions'),
        token_key=key,
        store=bool(token_data.get('store')),
        country=token_data.get('country') or None,
        # is dealer
        td=bool(token_data.get('td')),
    ) if token_data else {}


# get auth data by token.key
async def get_auth_data(request: Request, key: str, allowed_lvl: int = ACCESS_LVL.FLEET) -> dict:
    assert SpaceApiClient
    # TODO: add cache
    token_data = await get_token_data(key)

    result = dict()
    if token_data:
        cid = token_data['cid']
        access_lvl = token_data['access_lvl']
        app_id = token_data['app_id']

        if allowed_lvl:
            if access_lvl < allowed_lvl:
                raise PermissionError()

            # request with tsp/space token
            if access_lvl > allowed_lvl:
                # app_id TODO: check if app exists (by app_id from header)
                if _app_id := request.headers.get('X-AppId'):
                    app_id = _app_id

                if _cid := request.headers.get('X-Cid'):
                    _cid = int(_cid)
                    # check on fleet or tsp lvl
                    # TODO: merge to one request. what?
                    acc_data = await get_fleet_data(_cid) or await get_tsp_data(_cid)
                    _access_lvl = acc_data.get('access_lvl') or 0

                    if access_lvl <= _access_lvl or _access_lvl < allowed_lvl:
                        logger.error(
                            f'get_auth_data: msg=bad force command, {cid=}, {app_id=}, token_id={token_data.get("id")}, {access_lvl=}, {_access_lvl=}')
                        raise PermissionError()

                    cid = _cid
                    access_lvl = _access_lvl

        # get subscription_id
        subscription_id = None
        if app_id and (subscrs := token_data.get('subscriptions')):
            if subscr := subscrs.get(app_id):
                subscription_id = subscr.get('subscription_id')

        result = dict(
            request_cid=token_data['cid'],
            request_access_lvl=token_data['access_lvl'],
            request_app_id=token_data['app_id'],
            token_id=token_data['token_id'],
            cid=cid,
            access_lvl=access_lvl,
            app_id=app_id,
            subscription_id=subscription_id,
            token_key=key,
            store=bool(token_data.get('store')),
            country=token_data.get('country'),
            td=token_data.get('td'),
        )
    return result


# base auth-callback for JSONRPCAiohttp
async def auth_cbck_base(request: Request, allowed_lvl: int = None) -> (int, dict):
    return await jsonrpc_auth_cbck(request, allowed_lvl)


# auth callback for jsonrpc2
async def jsonrpc_auth_cbck(request: Request, allowed_lvl: int = None) -> (int, dict):
    code, extra_data = 401, {}
    log_prefix = f'{__name__}::auth_cbck_base'

    # -- get data by token
    # auth data from aiohttp-request
    extra_data = request.get('extra_data', {})
    # or get auth data by token
    if not extra_data:
        if token_key := request.headers.get(get_auth_header_name(request.app)):
            extra_data = await get_auth_data(request, token_key, allowed_lvl)

    access_lvl = extra_data.get('access_lvl')
    if allowed_lvl and (not access_lvl or access_lvl < allowed_lvl):
        return code, extra_data

    # -- check access=lvl
    if extra_data:
        if not allowed_lvl or access_lvl == allowed_lvl:
            code = 200
        else:
            logger.warning(f'{log_prefix}: msg=token-acl is not allowed, {allowed_lvl=}, {extra_data=}')

    # -- check auth, return http-code and extra_data for rpc-handlers
    return code, extra_data
