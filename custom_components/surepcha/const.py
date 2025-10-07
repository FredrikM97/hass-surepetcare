""" "Constants for the Sure Petcare integration."""

from surepcio.enums import ProductId

DOMAIN = "surepcha"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"

TOKEN = "token"
CLIENT_DEVICE_ID = "client_device_id"
FACTORY = f"{DOMAIN}_factory"
TIMEOUT_API = 10
KEY_API = f"{DOMAIN}_api"
COORDINATOR_LIST = "coordinator_list"
COORDINATOR_DICT = "coordinator_dict"
COORDINATOR = "coordinator"
ENTRY_ID = "entry_id"
SCAN_INTERVAL = 300
POLLING_SPEED = "polling_speed"
LOCATION_INSIDE = "location_inside"
LOCATION_OUTSIDE = "location_outside"
OPTION_DEVICES = "devices"
DEVICE_OPTION = "device_option"
OPTIONS_FINISHED = "finished"
PRODUCT_ID = "product_id"
DEVICES = "devices"
NAME = "name"

FLAP_PRODUCTS = {
    ProductId.PET_DOOR,
    ProductId.DUAL_SCAN_PET_DOOR,
    ProductId.DUAL_SCAN_CONNECT,
}
