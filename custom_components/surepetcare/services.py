import logging


async def async_disable_debug_logging(call):
    logging.getLogger("custom_components.surepetcare").setLevel(logging.INFO)
    logging.getLogger("py_surepetcare").setLevel(logging.INFO)


async def async_enable_debug_logging(call):
    logging.getLogger("custom_components.surepetcare").setLevel(logging.DEBUG)
    logging.getLogger("py_surepetcare").setLevel(logging.DEBUG)
