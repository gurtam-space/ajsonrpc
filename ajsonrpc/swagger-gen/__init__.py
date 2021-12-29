"""
    Only for aiohttp with cls-methods handler types
    specification openapi 3.0.0: https://swagger.io/specification/
    Required: aiohttp, marshmallow
"""

"""
    Example:
    web_app.router.add_route(
        METH_GET,
        path,
        lambda request: json_response(data=generate_swagger_info(
            routes=app.manager.dispatcher.values(),
            description='',
            api_version=version,
            auth_header_name=auth_header_name,
            title=title,
            host='',
            contact={
                name: '',
                url: '',
                email: ''
            },
        ))
    )
"""

from .swagger_helper import generate_swagger_info
