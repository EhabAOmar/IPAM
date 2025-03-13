import ipaddress
import re
from napalm import get_network_driver
import os
import Cryptodome
from Cryptodome.Cipher import AES
import base64

SECRET_KEY = os.getenv("SECRET_KEY")


def route_scan(route_prefix,router_vendor, **device_info):
    if router_vendor == "Juniper":
        router_vendor = "junos"
    elif router_vendor == "Cisco":
        router_vendor = "ios"
    elif router_vendor == "Huawei":
        router_vendor = "huawei_vrp"

    try:
        driver = get_network_driver(router_vendor)
        device = driver(**device_info)
        device.open()

        route_network = ipaddress.IPv4Network(route_prefix)
        route_network_id = route_network.network_address
        route_network_mask = route_network.netmask
        route_network_prefixlen = route_network.prefixlen

        if router_vendor == "junos":
            route_output = device.get_route_to(route_prefix)
            route_list = route_output.keys()
            route_list_str = " ".join(route_list)


        elif router_vendor == "ios":
            command = f"show ip route {route_network_id} {route_network_mask} longer-prefixes"
            route_list_str = device.cli([command], )[command]


        elif router_vendor == "huawei_vrp":
            command =f"display ip routing-table {route_network_id} {route_network_prefixlen} longer-match"
            route_list_str = device.cli([command], )[command]


        if not route_list_str:
            return {"status": True,"online_status": "Inactive", "online_utilization": 0.00}

        else:
            pattern = "(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}"
            route_dict_list = re.findall(pattern, route_list_str)

            utilization = get_subnet_utilization(route_prefix, route_dict_list)
            return {"status": True, "online_status": "Active", "online_utilization": utilization}


    except Exception as e:
        print(f"exception: {e}")
        return {"status": False, "online_status": "", "online_utilization": None}

def router_connection_test(router_vendor, **device_info):
    if router_vendor == "Juniper":
        router_vendor = "junos"
    elif router_vendor == "Cisco":
        router_vendor = "ios"
    elif router_vendor == "Huawei":
        router_vendor = "huawei_vrp"

    try:
        driver = get_network_driver(router_vendor)
        device = driver(**device_info)
        device.open()

        return True

    except Exception as e:
        print(f"exception: {e}")
        return False


def get_subnet_utilization(main_subnet, subnet_dict):
    main_subnet = ipaddress.ip_network(main_subnet)
    main_subnet_total_ips = main_subnet.num_addresses

    subnet_list = [ipaddress.ip_network(subnet) for subnet in subnet_dict if ipaddress.ip_network(subnet).prefixlen > main_subnet.prefixlen]

    # need to not count the sub-addresses under the subnets to not to count them twice.
    utilized_ips = 0
    for subnet in subnet_list:
        pass_subnet = True
        for item in subnet_list:
            if subnet.subnet_of(item) and subnet!=item:
                pass_subnet = False
                break

        if pass_subnet:
            utilized_ips += subnet.num_addresses

    utilization = round((utilized_ips / main_subnet_total_ips) * 100,2)
    return utilization



def validate_ip(ip):
    try:
        ipaddress.IPv4Address(ip)
        return True
    except ipaddress.AddressValueError:
        return False

def validate_prefix_length(prefixlen):
    if int(prefixlen) in range(0,33):
        return True
    else:
        return False


def get_break_subnet(main_subnet_prefix, prefixlen):
    main_subnet = ipaddress.IPv4Network(main_subnet_prefix)
    subnets_list = list(main_subnet.subnets(new_prefix=prefixlen))
    child_subnets_list = []
    for subnet in subnets_list:
        data = {}
        data["subnet_prefix"] = str(subnet)
        data["subnet_id"] = str(subnet.network_address)
        data["subnet_mask"] = str(subnet.prefixlen)
        data["subnet_name"] = ""
        data["subnet_service"] = ""
        data["subnet_description"] = ""
        child_subnets_list.append(data)

    return child_subnets_list



def encrypt_password(password):
    # SECRET_KEY must be stored in OS as Environment variable. And must be 16 character long.
    # You may set it here as a string for testing for example: SECRET_KEY = "012345678901234".encode()
    SECRET_KEY = os.getenv("SECRET_KEY").encode()

    if SECRET_KEY is None:
        raise ValueError("SECRET_KEY is not set!. Please set it as an Environment Variable on your system with 16 Character.")
    cipher = AES.new(SECRET_KEY, AES.MODE_EAX)
    nonce = cipher.nonce  # Needed for decryption
    ciphertext, tag = cipher.encrypt_and_digest(password.encode('utf-8'))
    return base64.b64encode(nonce + ciphertext).decode('utf-8')

def decrypt_password(encrypted_password):
    encrypted_password = base64.b64decode(encrypted_password)
    nonce = encrypted_password[:16]  # Extract nonce
    ciphertext = encrypted_password[16:]  # Extract ciphertext

    # Retrieving the SECRET_KEY from OS environment variables
    SECRET_KEY = os.getenv("SECRET_KEY").encode()

    cipher = AES.new(SECRET_KEY, AES.MODE_EAX, nonce=nonce)
    decrypted_password = cipher.decrypt(ciphertext).decode('utf-8')
    return decrypted_password
