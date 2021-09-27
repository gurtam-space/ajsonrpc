import inspect


def is_invalid_params(func, *args, **kwargs):
    """
    Method:
        Validate pre-defined criteria, if any is True - function is invalid
        0. func should be callable
        1. kwargs should not have unexpected keywords
        2. remove kwargs.keys from func.parameters
        3. number of args should be <= remaining func.parameters
        4. number of args should be >= remaining func.parameters less default
    """
    # For builtin functions inspect.getargspec(funct) return error. If builtin
    # function generates TypeError, it is because of wrong parameters.
    if not inspect.isfunction(func):
        return True

    signature = inspect.signature(func)
    parameters = signature.parameters

    unexpected = set(kwargs.keys()) - set(parameters.keys())
    if len(unexpected) > 0:
        return True

    params = [
        parameter for name, parameter in parameters.items()
        if name not in kwargs
    ]
    params_required = [
        param for param in params
        if param.default is param.empty
    ]

    return not (len(params_required) <= len(args) <= len(params))


def calc_errors_from_vd(errors: dict, data_on_validate: dict={}) -> list:
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
            for msgs in errors[field_name].values():
                for msg in msgs:
                    result_errors.append(dict(
                        selector=field_name,
                        value=data_on_validate.get(field_name) if type(data_on_validate) == dict else data_on_validate,
                        reason=msg))

        else:
            raise ValueError(errors)

    return result_errors


# validate dict by schema
def validate_by_schema(schema, data: dict) -> {dict, list}:
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
