"""
A slightly better approach to reloading modules and function than the standard importlib.reload()
function. The functions in this module are for interactive used in a Python REPL.

* reload_module(module): reloads the given module and all its parent modules
* reload_function(func): reloads and returns the given function

NOTE: It might be possible that after the module or function has been reloaded that an extra
      import is needed to import the proper module attributes in your namespace.

Module dependency

When you make a change in a module or function that you are not calling directly, but call
through another function from another module, you need to reload the module where you made
the change and, after that, reload the function that calls that module.

Example:

    * module x.a contains function func_a
    * module x.b contains function func_b which calls func_a

    when you make a change in func_a you have to relaod the module x.a and then reload
    the function func_b:

    >>> from x.b import func_b
    >>> func_b()
    # make some changes in func_a
    >>> reload_module('x.a')
    >>> func_b = reload_function(func_b)
    >>> func_b()  # will show the changes done in func_a

"""
import importlib
import itertools
import typing
import types

import rich

from egse.exceptions import Abort


def reload_module(module: typing.Union[types.ModuleType, str], walk: bool = True):
    """
    Reloads the given module and all its parent modules. The modules will be reloaded starting
    from their top-level module. Reloading the 'egse.hexapod.symetry.puna' module will reload
    'egse', 'egse.hexapod', 'egse.hexapod.symetry', and 'egse.hexapod.symetry.puna' in that order.

    NOTE: If you pass the module argument as a module, make sure the top level module is
    imported in your session, or you will get a NameError. To prevent this (if you don't want
    to import the top-level module, pass the module as a string.

    Usage:
        >>> import egse
        >>> reload_module(egse.system)
    or
        >>> reload_module('egse.system')

    Args:
        module: The module that needs to be reloaded
        walk: walk up the module hierarchy and import all modules [default=True]

    """
    full_module_name = module.__name__ if isinstance(module, types.ModuleType) else module

    module_names = itertools.accumulate(full_module_name.split('.'),
                                        lambda x, y: f"{x}.{y}") if walk else [full_module_name]

    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
            importlib.reload(module)
        except (Exception,) as exc:
            rich.print(f'[red]Failed to reload {module_name}[/red], {exc=}')


def reload_function(func: types.FunctionType):
    """
    Reloads and returns the given function. In order for this to work, you should catch the
    return value to replace the given function with its reloaded counterpart.

    This will also work if you import the function again instead of catching it.

    NOTE: that this mechanism doesn't work for functions that were defined in the __main__ module.

    Usage:
        func = reload_function(func)

        reload_function(func)
        from egse.some_module import func

    Args:
        func: the function that needs to be reloaded

    Returns:
        The reloaded function.

    Raises:
        An Abort when the function is not the proper type or when the function is defined
        in the __main__ module.
    """

    # Why do I raise an Abort instead of just printing a message and returning?
    #
    # The function is usually called catching the return value and replacing the same function with
    # its reloaded counterpart. If we would just return (None) when an error occurs, the original
    # function will be overwritten with None. Raising an Exception leaves the original as it was
    # before the call.

    if not isinstance(func, types.FunctionType):
        raise Abort(f"The 'func' argument shall be a function, not {type(func)}")

    module_name = func.__module__
    func_name = func.__name__

    if module_name == '__main__':
        raise Abort("Cannot reload a function that is defined in the __main__ module.")

    reload_module(module_name)

    module = __import__(module_name, fromlist=[func_name])
    return getattr(module, func_name)
