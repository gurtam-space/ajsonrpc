try:
    import ujson as json
except Exception:
    import json
from marshmallow import UnmarshalResult, Schema, fields as m_fields
from aiohttp.web_request import Request


def calc_errors_from_vd(errors: dict, data_on_validate: dict = {}) -> list:
    """ calc errors from validate-data (errors) by UnmarshalResult """
    result_errors = []
    # errors = {field_name: [errors-msgs]}
    for field_name in errors:
        if isinstance(errors[field_name], list):
            for msg in errors[field_name]:
                result_errors.append(dict(
                    selector=field_name,
                    value=data_on_validate.get(field_name) if type(data_on_validate) == dict else data_on_validate,
                    reason=msg))

        elif isinstance(errors[field_name], dict):
            for el_num in errors[field_name]:
                msgs = errors[field_name][el_num]
                from typing import Iterable

                for msg in msgs:
                    value = data_on_validate.get(field_name) if type(data_on_validate) == dict else data_on_validate
                    if not isinstance(value, str) and isinstance(value, Iterable):
                        value = value[el_num]
                    result_errors.append(dict(
                        selector=f'{field_name}.{el_num}',
                        value=value,
                        reason=msg))

        else:
            raise ValueError(errors)

    return result_errors


# validate dict by schema
def validate_by_schema(schema: Schema, data: dict) -> {dict, list}:
    assert Schema and m_fields
    """ validate dict by marshmallow.Schema """
    # validate-data, errors
    v_data, errors = {}, []
    # validate
    v_errors = schema.validate(data)
    if v_errors:
        errors.extend(calc_errors_from_vd(errors=v_errors, data_on_validate=data))
    else:
        v_data, v_errors = schema.dump(data)
        if v_errors:
            errors.extend(calc_errors_from_vd(errors=v_errors, data_on_validate=data))
    return v_data, errors


# return get-params from request or error validate
def calc_request_get_params(schema: Schema, request: Request) -> (dict, list):
    assert Schema and m_fields
    # calculate params
    params = {}

    # -- get params from request
    for param_name in schema.fields:
        if param_name not in request.match_info and param_name not in request.query:
            continue
        # param-value, select from request
        p = request.match_info.get(param_name) or request.query.get(param_name)
        # schema.type
        f_type = schema.fields[param_name]
        # list
        if isinstance(f_type, m_fields.List):
            if type(p) not in (list, set, tuple):
                # TODO: or json.loads?
                p = str(p).split(',') if p else []
        # dict
        elif isinstance(f_type, (m_fields.Dict, m_fields.Nested)):
            if isinstance(p, str):
                p = json.loads(p)
        elif p is not None:
            pass
        if p is not None:
            params[param_name] = p

    # -- validate
    result, errors = validate_by_schema(schema, params) if params else ({}, [])

    return result, errors


# standard result item
def get_result_item(data, fields, fields_dict: dict = {}, filter_isset: bool = False) -> dict:
    """
    :param data: dict or object withs function get(field_name)
    :param fields: list or set
    :param fields_dict: dict { alias: field_name }
    :return: dict
    """
    result = {}
    # function getter field from data
    getter = dict.get if isinstance(data, dict) else getattr
    has_attr = f = lambda obj, name: name in obj if isinstance(data, dict) else hasattr
    for field in fields:
        if not filter_isset or has_attr(data, field):
            # value field getter: string or function
            field_getter = fields_dict.get(field, field)
            if isinstance(field_getter, str):
                result[field] = getter(data, field_getter, None)
            else:
                result[field] = field_getter(data)
    return result
