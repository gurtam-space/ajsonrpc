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


# get auth data by token.key
async def get_auth_data(key: str) -> dict:
    assert SpaceApiClient
    token_data, errs = await SpaceApiClient().sun_state.one_request(
        SpaceApiClient().sun_state.methods.dstate['search'],
        dict(
            entity='token',
            c=[['key', key, 'eq']],
            count=1,
            fields=['id', 'cid', 'access_lvl', 'subscription']
        )
    )
    if errs:
        logger.error(f'get_auth_data: msg=fail getting token, {key=}, {errs=}')

    return dict(
        cid=token_data['cid'],
        token_id=token_data['id'],
        access_lvl=token_data['access_lvl'],
        subscription_id=subscription.get('subscription_id') or None if (subscription := token_data.get('subscription')) else None,
        token=key,
    ) if token_data else {}


# base auth-callback for JSONRPCAiohttp
async def auth_cbck_base(request: Request, access_lvl: int = None) -> (int, dict):
    code, extra_data = 401, {}

    # -- get data by token
    extra_data = request.get('extra_data', {})
    if not extra_data:
        if token_key := request.headers.get(get_auth_header_name(request.app)):
            extra_data = await get_auth_data(token_key)

    # -- check access=lvl
    if extra_data:
        if not access_lvl or extra_data['access_lvl'] == access_lvl:
            code = 200
        else:
            logger.warning(f'auth_cbck_base: msg=token-acl is not allowed, {access_lvl=}, {extra_data=}')

    # -- check auth, return http-code and extra_data for rpc-handlers
    return code, extra_data
