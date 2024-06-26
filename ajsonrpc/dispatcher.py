"""Method name to method mapper.

Dispatcher is a dict-like object which maps method_name to method.
For usage examples see :meth:`~Dispatcher.add_function`

"""
import functools
import inspect
import types
from typing import Any, Optional, Mapping
from collections.abc import Mapping as CollectionsMapping, MutableMapping, Callable
from dataclasses import dataclass, field

import logging
logger = logging.getLogger()


@dataclass
class MethodSettings:
    # class
    cls: object
    # name function for running
    func_name: str
    # name command
    name: str
    # marshmallow schema for validation params
    schema: object = field(default=None)
    # marshmallow schema for validation response
    response_schema: object = field(default=None)
    # is deprecated method
    deprecated: bool = field(default=None)
    # acl schema, example: { module_name: min_lvl, }
    # check with request.extra_data['user_acl'], user acl example: { module_name: access_lvl, }
    acl: dict = field(default=None)
    # function that get user_acl and return true or false
    acl_func: types.FunctionType = field(default=None)


class Dispatcher(MutableMapping):

    """Dictionary-like object which maps method_name to method."""

    def __init__(self, prototype: Any = None, prefix: Optional[str] = None) -> None:
        """ Build method dispatcher.

        Parameters
        ----------
        prototype : object or dict, optional
            Initial method mapping.

        Examples
        --------

        Init object with method dictionary.

        >>> Dispatcher({"sum": lambda a, b: a + b})
        None

        """
        self.method_map: Mapping[str, Callable] = dict()

        if prototype is not None:
            self.add_prototype(prototype, prefix=prefix)

    def __getitem__(self, key: str) -> Callable:
        return self.method_map[key]

    def __setitem__(self, key: str, value: Callable) -> None:
        self.method_map[key] = value

    def __delitem__(self, key: str) -> None:
        del self.method_map[key]

    def __len__(self):
        return len(self.method_map)

    def __iter__(self):
        return iter(self.method_map)

    def __repr__(self):
        return repr(self.method_map)

    @staticmethod
    def _getattr_function(prototype: Any, attr: str) -> Callable:
        """Fix the issue of accessing instance method of a class.

        Class.method(self, *args **kwargs) requires the first argument to be
        instance, but it was not given. Substitute method with a partial
        function where the first argument is an empty class constructor.

        """

        method = getattr(prototype, attr)
        if inspect.isclass(prototype) and isinstance(prototype.__dict__[attr], types.FunctionType):
            return functools.partial(method, prototype())
        return method

    @staticmethod
    def _extract_methods(prototype: Any, prefix: str = "") -> Mapping[str, Callable]:
        return {
            prefix + attr: Dispatcher._getattr_function(prototype, attr)
            for attr in dir(prototype)
            if not attr.startswith("_")
        }

    def add_class(self, cls: Any, prefix: Optional[str] = None) -> None:
        """Add class to dispatcher.

        Adds all of the public methods to dispatcher.

        Notes
        -----
            If class has instance methods (e.g. no @classmethod decorator),
            they likely would not work. Use :meth:`~add_object` instead.
            At the moment, dispatcher creates an object with empty constructor
            for instance methods.

        Parameters
        ----------
        cls : type
            class with methods to be added to dispatcher
        prefix : str, optional
            Method prefix. If not present, lowercased class name is used.

        """
        if prefix is None:
            prefix = cls.__name__.lower() + '.'

        self.update(Dispatcher._extract_methods(cls, prefix=prefix))

    def add_class_method(self, cls: Any, func_name: str, prefix: Optional[str] = None,
                         schema = None,
                         acl: dict = None,
                         acl_func: types.FunctionType = None,
                         deprecated: bool = None,
                         response_schema = None) -> None:
        """
        schema: marshmallow.Schema for validation params
        """
        # check function in class
        if prefix is None:
            prefix = cls.__name__.lower() + '.'

        method = f'{prefix}{func_name}'
        logger.debug(f'{self.__class__.__name__}::add_class_method: msg=add method, name={method}')

        self[method] = MethodSettings(
            cls=cls,
            func_name=func_name,
            schema=schema,
            acl=acl,
            acl_func=acl_func,
            name=method,
            deprecated=deprecated,
            response_schema=response_schema,
        )

    def add_object(self, obj: Any, prefix: Optional[str] = None) -> None:
        if prefix is None:
            prefix = obj.__class__.__name__.lower() + '.'

        self.update(Dispatcher._extract_methods(obj, prefix=prefix))

    def add_prototype(self, prototype: Any, prefix: Optional[str] = None) -> None:
        if isinstance(prototype, CollectionsMapping):
            self.update({
                (prefix or "") + key: value
                for key, value in prototype.items()
            })
        elif inspect.isclass(prototype):
            self.add_class(prototype, prefix=prefix)
        else:
            self.add_object(prototype, prefix=prefix)

    def add_function(self, f: Callable = None, name: Optional[str] = None) -> Callable:
        """ Add a method to the dispatcher.

        Parameters
        ----------
        f : callable
            Callable to be added.
        name : str, optional
            Name to register (the default is function **f** name)

        Notes
        -----
        When used as a decorator keeps callable object unmodified.

        Examples
        --------

        Use as method

        >>> d = Dispatcher()
        >>> d.add_function(lambda a, b: a + b, name="sum")
        <function __main__.<lambda>>

        Or use as decorator

        >>> d = Dispatcher()
        >>> @d.add_function
            def mymethod(*args, **kwargs):
                print(args, kwargs)

        Or use as a decorator with a different function name
        >>> d = Dispatcher()
        >>> @d.add_function(name="my.method")
            def mymethod(*args, **kwargs):
                print(args, kwargs)

        """
        if name and not f:
            return functools.partial(self.add_function, name=name)

        self[name or f.__name__] = f
        return f
