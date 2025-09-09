import logging

_service_registry = []

def service(name):
    def decorator(func):
        _service_registry.append((name, func))
        return func
    return decorator

@service("disable_debug_logging")
async def async_disable_debug_logging(call):
    logging.getLogger("custom_components.surepetcare").setLevel(logging.INFO)
    logging.getLogger("py_surepetcare").setLevel(logging.INFO)

@service("enable_debug_logging")
async def async_enable_debug_logging(call):
    logging.getLogger("custom_components.surepetcare").setLevel(logging.DEBUG)
    logging.getLogger("py_surepetcare").setLevel(logging.DEBUG)
