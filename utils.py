import ipaddress
import re
from napalm import get_network_driver


def route_scan(route_prefix,router_vendor, **device_info):
    if router_vendor == "juniper":
        router_vendor = "junos"
    elif router_vendor == "cisco":
        router_vendor = "ios"
    elif router_vendor == "huawei":
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
            route_dict = device.get_route_to(route_prefix)

        elif router_vendor == "ios":
            command = f"show ip route {route_network_id} {route_network_mask} longer-prefixes"
            route_dict = device.cli([command], )[command]

            pattern = "(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}"
            route_dict_list = re.findall(pattern,route_dict)

        elif router_vendor == "huawei_vrp":
            command =f"display ip routing-table {route_network_id} {route_network_prefixlen} longer-match"
            route_dict = device.cli([command], )[command]

            pattern = "(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}"
            route_dict_list = re.findall(pattern,route_dict)

        if not route_dict:
            return {"status": True,"online_status": "Inactive", "online_utilization": 0.00}

        else:
            if router_vendor =="junos":
                route_dict_list = list(route_dict.keys())

            utilization = get_subnet_utilization(route_prefix, route_dict_list)
            return {"status": True, "online_status": "Active", "online_utilization": utilization}


    except Exception as e:
        print(f"exception: {e}")
        return {"status": False, "online_status": "", "online_utilization": None}

def router_connection_test(router_vendor, **device_info):
    if router_vendor.lower() == "juniper":
        router_vendor = "junos"
    elif router_vendor.lower() == "cisco":
        router_vendor = "ios"
    elif router_vendor.lower() == "huawei":
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
        child_subnets_list.append(data)

    return child_subnets_list
