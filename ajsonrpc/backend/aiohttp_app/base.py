
AUTH_HEADER_NAME_BASE = 'X-AccessToken'


# set header name with access token
def set_auth_header_name(app: object, value: str):
    setattr(app, '_auth_header_name', value)


# get header name with access token
def get_auth_header_name(app: object) -> str:
    return getattr(app, '_auth_header_name', AUTH_HEADER_NAME_BASE)
