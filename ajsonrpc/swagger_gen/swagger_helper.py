from os.path import abspath, dirname, join
# import types
# import yaml
# from jinja2 import Template
# from typing import Union
from aiohttp.hdrs import METH_POST
from marshmallow import fields

from ..dispatcher import MethodSettings

import logging
logger = logging.getLogger()

# try:
#     import ujson as json
# except ImportError:
#     import json


SWAGGER_TEMPLATE = abspath(join(dirname(__file__), "templates"))

# class method docstring separator that is used to separate path summary and description
DOCSTRING_SEPARATOR = '\n'
# method of request
REQUEST_METHOD = METH_POST


# todo: FIX ADD REQUIRED FIELDS

# get swagger data type
def get_data_type(param_field):
    if isinstance(param_field, fields.Integer):
        return 'integer'

    if isinstance(param_field, fields.Float):
        return 'number'

    if isinstance(param_field, fields.Boolean):
        return 'boolean'

    if isinstance(param_field, fields.List):
        return 'array'

    if isinstance(param_field, fields.Dict):
        return 'object'

    if isinstance(param_field, fields.Nested):
        return 'nested'

    return 'string'


# get schema props
def get_schema_props(schema_fields) -> (dict, list):
    schema_props = {}
    required_names = []
    for param_field in schema_fields.values():
        if not param_field.dump_only:
            # get swagger data type
            data_type = get_data_type(param_field)

            obj = {
                # 'description': param_field.name,
                # 'required': param_field.required,
                # 'default': param_field.default if param_field.default else '',
                'type': data_type,
            }
            if param_field.default:
                obj['default'] = param_field.default

            if param_field.required:
                # object['required'] = param_field.required
                required_names.append(param_field.name)

            # add items property if type is array
            if data_type == 'array':
                obj['items'] = {
                    'type': get_data_type(param_field.container)
                }

            if data_type == 'nested':
                obj['type'] = 'object'
                pr, req = get_schema_props(param_field.nested.fields)
                obj['properties'] = pr
                obj['required'] = req

            schema_props[param_field.name] = obj
    return schema_props, required_names


# create dict with Swagger data
# contact example: {name: str, url: str, email: str}
def generate_swagger_info(
        routes: list,
        path: str,
        description: str,
        api_version: str,
        auth_header_name: str,
        title: str,
        hosts: list,
        contact: dict = None,
) -> dict:
    # Load base Swagger template
    # with open(join(SWAGGER_TEMPLATE, "swagger.json"), "r") as f:
    #     swagger_base = (
    #         Template(f.read()).render(
    #             description=description,
    #             version=api_version,
    #             title=title,
    #             contact=contact,
    #             host=host)
    #     )
    #
    # # The Swagger OBJ
    # swagger = yaml.safe_load(swagger_base)

    # result swagger config
    result = dict(
        openapi='3.0.0',
        info=dict(
            title=title,
            description=description,
            contact=contact,
            version=api_version,
        ),
        servers=[dict(url=addr) for addr in hosts],
        paths=dict(),
        components=dict(
            securitySchemes=dict(),
            schemas=dict(),
        ),
        security=[],
        tags=[]
    )
    print(23423)
    # if isset access-token - add header
    if auth_header_name:
        result['components']['securitySchemes'] = {
            auth_header_name: {
                'type': 'apiKey',
                'name': auth_header_name,
                'in': 'header'
            }
        }
        result['security'].append({
            auth_header_name: []
        })

    # tags, schemas for swagger
    tags = []
    tag_names = []
    schemas = {}

    for method_cfg in routes:  # type: MethodSettings
        # -- method data
        handler_cls = method_cfg.cls
        func_name = method_cfg.func_name
        schema = method_cfg.schema
        method_name = method_cfg.name

        route_path = f'{path}#{method_name}'

        # -- tags
        if handler_cls.__name__ not in tag_names:
            # add new tag
            tag_object = {'name': handler_cls.__name__}
            if handler_cls.__doc__:
                tag_object['description'] = handler_cls.__doc__

            tags.append(tag_object)
            tag_names.append(handler_cls.__name__)

        # -- class method docstring
        method_docstring = getattr(handler_cls, func_name).__doc__ or ''
        split_docstring = list(map(lambda str: str.strip(), method_docstring.split(DOCSTRING_SEPARATOR, 2)))

        end_point_doc_by_method = {
            'tags': [handler_cls.__name__],
            'summary': split_docstring[0],
            'description': '<br>'.join(split_docstring),
            # 'parameters': [],
            'responses': {
                '200': {
                    'description': 'successful operation',
                    'content': {'application/json': {}}
                }
            }
        }

        # # -- calc get-params
        # if schema:
        #     for param_field in schema.fields.values():
        #         # calc type get-param
        #         if '{%s}' % param_field.name in route_path:
        #             param_in = 'path'
        #         else:
        #             param_in = 'query'
        #
        #         # get swagger data type
        #         data_type = get_data_type(param_field)
        #
        #         object_to_append = {
        #             'in': param_in,
        #             'name': param_field.name,
        #             'schema': {
        #                 'default': param_field.default if param_field.default else '',
        #                 'type': data_type
        #             },
        #             'required': True if param_in == 'path' else param_field.required
        #         }
        #
        #         # add items property if type is array
        #         if data_type == 'array':
        #             object_to_append['schema']['items'] = {
        #                 'type': get_data_type(param_field.container)
        #             }
        #
        #         end_point_doc_by_method['parameters'].append(object_to_append)

        # -- body-params
        data = {
            'schema_props': {},
            'required': []
        }
        # if there is schema
        if schema:
            if type(schema) == dict:
                logger.error(f'generate_swagger_info: msg=not implemented dict schemas, go fix code!')
                # data = []
                # for key in schema:
                #     sp, rn = get_schema_props(schema[key].fields)
                #     data.append({
                #         'name': key,
                #         'schema_props': sp,
                #         'required': rn
                #     })
            else:
                schema_props = {
                    'jsonrpc': {
                        'default': '2.0',
                        'type': 'string'
                    },
                    'id': {
                        'default': 'request1',
                        'type': 'string'
                    },
                    'method': {
                        # TODO: add prefix
                        'default': f'{method_name}',
                        'type': 'string'
                    },
                }
                required = ['jsonrpc', 'method']
                sp, rn = get_schema_props(schema.fields)
                if sp:
                    schema_props['params'] = {
                        'type': 'object',
                        'properties': sp,
                        # 'required': rn
                    }
                if rn:
                    required.append('params')
                data['schema_props'] = schema_props
                # data['required'] = required

        if type(data) == list:
            logger.error(f'generate_swagger_info: msg=not implemented dict schemas, go fix code!')
            # one_of = []
            # for item in data:
            #     definition_name = schema.__class__.__name__
            #     # add definition
            #     schemas[definition_name] = {
            #         'type': 'object',
            #         'required': item['required'],
            #         'properties': item['schema_props']
            #     }
            #     # one_of.append({ '$ref': '#/components/schemas/{}'.format(definition_name) })
            #     one_of.append({'type': 'array', 'items': {'$ref': '#/components/schemas/{}'.format(definition_name)}})
            #
            # # add body-params
            # end_point_doc_by_method['requestBody'] = {
            #     'required': True,
            #     'content': {
            #         'application/json': {
            #             'schema': {
            #                 'oneOf': one_of
            #             }
            #         }
            #     }
            # }
        else:
            definition_name = schema.__class__.__name__
            # add definition
            end_point_doc_by_method['requestBody'] = {
                'required': True,
                'content': {
                    'application/json': {
                        'schema': {
                            'type': 'object',
                            '$ref': f'#/components/schemas/{definition_name}'
                        }
                    }
                }
            }
            schemas[definition_name] = {
                'type': 'object',
                # 'required': data['required'],
                'properties': data['schema_props']
            }
            # add body-params

        # add to docs
        result['paths'].setdefault(route_path, {})
        result['paths'][route_path][REQUEST_METHOD.lower()] = end_point_doc_by_method

    # set tags, schemas
    result['tags'] = tags
    result['components']['schemas'] = schemas

    return result
