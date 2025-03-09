from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from typing import List
from fastapi.staticfiles import StaticFiles
import ipaddress
from utils import route_scan, router_connection_test, get_subnet_utilization, validate_ip, validate_prefix_length, get_break_subnet, encrypt_password, decrypt_password

# data structure used is tree for the subnets, each subnet can have many children. The link between the node and its parent is "subnet_parent".


app = FastAPI()

# MongoDB connection
MONGO_URI = "mongodb://localhost:27017"
client = AsyncIOMotorClient(MONGO_URI)


db = client.network_db

# database for subnets
collection = db.subnets

# database for routers
router_collection = db.routers


# Serve static files from "static" folder
app.mount("/static", StaticFiles(directory="static"), name="static")


templates = Jinja2Templates(directory="templates")
documentations = Jinja2Templates(directory="docs")


# Pydantic model for validation
class Subnet(BaseModel):
    subnet_prefix: str = Field(...)
    subnet_id: str = Field(...)
    subnet_mask: str = Field(...)
    subnet_root: str = None
    subnet_parent: str = None
    subnet_name: str = Field(...)
    subnet_description: str = Field(...)
    offline_utilization: float = 0.00
    online_status: str = ""
    online_utilization: float = 0.00

class Router(BaseModel):
    router_ip: str = Field(...)
    router_name: str = Field(...)
    router_username: str = Field(...)
    router_password: str = Field(...)
    router_vendor: str = Field(...)


# Home Page
@app.get("/")
async def serve_index(request: Request):
    subnets = await collection.find().to_list()
    major_subnets = [subnet for subnet in subnets if subnet['subnet_prefix'] == subnet['subnet_root']]
    return templates.TemplateResponse("index.html", {"request": request, "subnets": major_subnets})



# About Page
@app.get("/docs/about")
async def about(request: Request):
    return documentations.TemplateResponse("about.html", {"request": request})

# Help Page
@app.get("/docs/help")
async def help(request: Request):
    return documentations.TemplateResponse("help.html", {"request": request})



# List all Routers
@app.get("/routers")
async def list_routers(request: Request):
    routers = await router_collection.find().to_list(length=2)

    for router in routers:
        router["_id"] = str(router["_id"])  # Convert Router ObjectId to String

    return templates.TemplateResponse("router_detail.html", {"request": request, "routers": routers})


# Go to add router Page
@app.get("/add-router")
async def add_router_page(request: Request):
    return templates.TemplateResponse("add_router.html", {"request": request})



# Add a new router
@app.post("/routers/")
async def add_router(router: Router):
    existing_router = await router_collection.find_one({"router_ip": router.router_ip})

    if existing_router:
        raise HTTPException(status_code=400, detail="Router already exists")

    # Limit is two routers. One is main and other is backup
    all_existing_routers = await router_collection.find().to_list()
    if len(all_existing_routers) == 2:
        raise HTTPException(status_code=400, detail="Limit exceeded, there are already two Routers.")

    router_dict = router.model_dump()
    router_dict['router_password'] = encrypt_password(router_dict['router_password'])
    await router_collection.insert_one(router_dict)
    return {"message": "Router added successfully"}


# Update Router. Update fields are Router's Name, Username, Password and Vendor.
@app.put("/routers/{router_id}")
async def update_router(router_id: str, updateData: dict):
    object_id = ObjectId(router_id)  # Convert String to ObjectId
    router = await router_collection.find_one({"_id": object_id})

    if not router:
        raise HTTPException(status_code=404, detail="Router not found")

    updateData['router_password'] = encrypt_password(updateData['router_password'])

    await router_collection.update_one({"_id": router["_id"]},{"$set": updateData})
    return {"success": True}



# Delete Router
@app.delete("/routers/{router_id}")
async def delete_router(router_id: str):
    object_id = ObjectId(router_id)   # Convert String to ObjectId
    result = await router_collection.delete_one({"_id": object_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Router not found")

    return {"message": f"Router Deleted Successfully"}



# Test Router Connection
@app.get("/routers/testconnection/{router_id}")
async def testConnection(router_id: str):
    object_id = ObjectId(router_id)   # Convert String to ObjectId
    router = await router_collection.find_one({"_id": object_id})
    router['router_password'] = decrypt_password(router['router_password'])

    device_info = {"hostname": router['router_ip'], "username": router['router_username'], "password": router['router_password'] }

    # Test if SSH to router is successful using the input username and password
    result = router_connection_test(router['router_vendor'], **device_info)

    if result:
        return {"message": "Test Connection success"}
    else:
        return {"message": "Test Connection Failed"}




# Add Major Subnet Page
@app.get("/add-major-subnet")
async def add_subnet_page(request: Request):
    return templates.TemplateResponse("add_major_subnet.html", {"request": request})



# Subnet Detail Page
@app.get("/subnets/{subnet_id}-{subnet_mask}")
async def get_subnet_detail(request: Request, subnet_id: str, subnet_mask: str):
    main_subnet_prefix = f"{subnet_id}/{subnet_mask}"
    main_subnet = await collection.find_one({"subnet_prefix": main_subnet_prefix })

    if not main_subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    # Get all active children subnets under the selected main subnet
    all_subnets = await collection.find({"subnet_parent":main_subnet_prefix}).to_list()

    for subnet in all_subnets:
        subnet["_id"] = str(subnet["_id"])  # Convert ObjectId to String
    return templates.TemplateResponse("subnet_detail.html", {"request": request, "subnet": main_subnet, "subnets": all_subnets})



# Add a new Major subnet
@app.post("/subnets/")
async def add_major_subnet(subnet: Subnet):
    # Check if the new added subnet already exist
    existing_subnet = await collection.find_one({"subnet_prefix": subnet.subnet_prefix})

    if existing_subnet:
        raise HTTPException(status_code=400, detail="Major Subnet already exists")

    subnet_dict = subnet.model_dump()

    await collection.insert_one(subnet_dict)
    return {"message": "Subnet added successfully"}



# Delete one or multiple subnets by ObjectId
@app.delete("/subnets/")
async def delete_subnets(ids: List[str]):

    # Delete the subnet only if it has no child subnets
    for id in ids:
        object_id = ObjectId(id)
        subnet = await collection.find_one({"_id": object_id})
        subnet_prefix = subnet['subnet_prefix']
        child_subnets = await collection.find({"subnet_parent":subnet_prefix}).to_list()

        if child_subnets:
            ids.remove(id)
            raise HTTPException(status_code=400, detail="The subnet contains active smaller subnet(s). Cant' be deleted!")

    if ids:
        object_ids = [ObjectId(id) for id in ids]  # Convert String to ObjectId


        # Gather Parent subnet IDs, to update their utilization later.
        upper_subnet_prefixes = []

        for object_id in object_ids:
            subnet = await collection.find_one({"_id": object_id})
            upper_subnet_prefix = subnet['subnet_parent']
            if (upper_subnet_prefix not in upper_subnet_prefixes) and upper_subnet_prefix != "":
                upper_subnet_prefixes.append(upper_subnet_prefix)

        result = await collection.delete_many({"_id": {"$in": object_ids}})

        if result.deleted_count == 0:
            raise HTTPException(status_code=400, detail="The subnet contains active smaller subnet(s). Cant' be deleted!")


        # Update utilization for parent subnets
        for upper_subnet_prefix in upper_subnet_prefixes:
            all_upper_children = await collection.find({"subnet_parent": upper_subnet_prefix}).to_list()
            all_upper_children_subnets = []
            for child in all_upper_children:
                all_upper_children_subnets.append(child['subnet_prefix'])

            utilization = get_subnet_utilization(upper_subnet_prefix,all_upper_children_subnets)
            await collection.update_one({"subnet_prefix": upper_subnet_prefix},{"$set": {"offline_utilization": utilization}})


        return {"message": f"Deleted {result.deleted_count} subnets"}



# Update a subnet
@app.put("/subnets/{id}")
async def update_subnet(id: str, updateData: dict):

    object_id = ObjectId(id)  # Convert String to ObjectId
    existing_subnet = await collection.find_one({"_id": object_id})

    if not existing_subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    await collection.update_one({"_id": existing_subnet["_id"]},{"$set": updateData})

    return {"success": True}



# Scan a subnet, which means check if the subnet exist in live network.
@app.put("/scan_subnet/")
async def scan_subnet(data: dict):
    subnet_prefix= data['subnet_prefix']
    existing_subnet = await collection.find_one({"subnet_prefix": subnet_prefix})

    if not existing_subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    routers = await router_collection.find().to_list()   #return the two routers

    if not routers:
        raise HTTPException(status_code=404, detail="Router not found. Please add Router first")

    main_router = routers[0]
    router_vendor = main_router['router_vendor']
    main_router['router_password'] = decrypt_password(main_router['router_password'])
    router_device_info = {"hostname": main_router['router_ip'], "username": main_router['router_username'], "password": main_router['router_password'] }

    connection_status_to_main_router = router_connection_test(router_vendor, **router_device_info)

    # If connection failed to the main router, and no backup router, raise error.
    if not connection_status_to_main_router and len(routers) == 1:
        raise HTTPException(status_code=400, detail="Can't Connect to Router")

    # If connection failed to the main router, proceed with the backup router if exists.
    if not connection_status_to_main_router and len(routers)==2:
        backup_router = routers[1]
        router_vendor = backup_router['router_vendor']
        backup_router['router_password'] = decrypt_password(backup_router['router_password'])
        router_device_info = {"hostname": backup_router['router_ip'], "username": backup_router['router_username'], "password": backup_router['router_password'] }

        if not router_connection_test(router_vendor, **router_device_info):
            raise HTTPException(status_code=400, detail="Can't Connect to Routers")

    scan_result = route_scan(subnet_prefix, router_vendor, **router_device_info)

    # If route successfully was queried from the router, then update the scan results with online status and utilization.
    if scan_result['status']:
        update_data = {
            "online_status": scan_result['online_status'],
            "online_utilization": scan_result['online_utilization']
        }

        await collection.update_one(
            {"_id": existing_subnet["_id"]},
            {"$set": update_data}
        )

        return {"message": "Subnet Scanned Successfully"}

    return {"message": "Connection to Router Failed"}


# Scan a subnet, which means check if the subnet exist in live network.
@app.put("/scan_subnets/")
async def scan_subnets(ids: List[str]):
    for id in ids:
        object_id = ObjectId(id)
        subnet = await collection.find_one({"_id": object_id})
        subnet_prefix = subnet['subnet_prefix']
        data = {"subnet_prefix": subnet_prefix}
        await scan_subnet(data)



# Break a subnet, means to divide a subnet into smaller subnets.
@app.put("/break_subnet/")
async def break_subnet(data: dict):
    main_subnet_prefix= data['subnet_prefix']
    break_prefixlen = data ['break_prefixlen']
    main_subnet_id,main_subnet_mask = main_subnet_prefix.split("/")
    break_prefixlen = int(break_prefixlen.strip("/")) # convert the prefix length from /xx string format to integer number xx

    # Check if the subnet already has child subnets, at least one.
    existing_child_subnet = await collection.find_one({"subnet_parent": main_subnet_prefix})

    if  existing_child_subnet:
        raise HTTPException(status_code=400, detail="Subnet already contains smaller subnet(s). You should delete them first before breaking it.")

    child_subnets_list = get_break_subnet(main_subnet_prefix,break_prefixlen)
    for child_subnet in child_subnets_list:
        child_subnet_data = Subnet(
        subnet_prefix=child_subnet["subnet_prefix"],
        subnet_id = child_subnet["subnet_id"],
        subnet_mask = child_subnet["subnet_mask"],
        subnet_name = child_subnet["subnet_name"],
        subnet_description = child_subnet["subnet_description"]
        )
        await add_subnet(main_subnet_id,main_subnet_mask,child_subnet_data)


    return {"message": "Subnet has been divided successfully"}




# Get subnet information under subnet
@app.get("/subnets/{main_subnet_id}-{main_subnet_mask}/add-subnet")
async def add_subnet_form(request: Request, main_subnet_id: str, main_subnet_mask: str):
    return templates.TemplateResponse("add_subnet.html", {"request": request,"main_subnet_id": main_subnet_id, "main_subnet_mask": main_subnet_mask})



# Add subnet under Upper subnet
@app.post("/subnets/{upper_subnet_id}-{upper_subnet_mask}/add-subnet")
async def add_subnet(upper_subnet_id: str, upper_subnet_mask: str, subnet: Subnet):

    # removing white spaces for the new subnet
    subnet.subnet_id = subnet.subnet_id.strip()
    subnet.subnet_mask = subnet.subnet_mask.strip()
    subnet.subnet_prefix = f"{subnet.subnet_id}/{subnet.subnet_mask}"


    # Validate subnet_id is an IP address format
    if not validate_ip(subnet.subnet_id):
        raise HTTPException(status_code=400, detail="Wrong subnet ID!")

    # Validating subnet mask/prefix-length in the range from 0 to 32
    if not validate_prefix_length(subnet.subnet_mask):
        raise HTTPException(status_code=400, detail="Wrong subnet Mask, Please input mask in range (0 to 32) !")

    # Forming upper subnet prefix
    upper_subnet_prefix = f"{upper_subnet_id}/{upper_subnet_mask}"

    # Getting the new subnet from DB, if exist
    existing_subnet = await collection.find_one({"subnet_prefix": subnet.subnet_prefix})

    # Extract root subnet
    upper_subnet = await collection.find_one({"subnet_prefix": upper_subnet_prefix})
    root_subnet = upper_subnet['subnet_root']
    root_subnet_network =  ipaddress.IPv4Network(root_subnet,strict=False)
    root_subnet_prefixlen = root_subnet_network.prefixlen

    if existing_subnet:
        raise HTTPException(status_code=400, detail="Subnet Already Exists.")


    # Subnet doesn't exist, create it and bind it to the parents subnet, and child subnets if exist.
    else:
        new_subnet_network = ipaddress.IPv4Network(subnet.subnet_prefix,strict=False)  # convert string subnet into class ipaddress
        upper_subnet_network = ipaddress.IPv4Network(upper_subnet_prefix,strict=False)  # convert string subnet into class ipaddress

        # Verify new subnet is part of the upper subnet.
        if not new_subnet_network.subnet_of(upper_subnet_network):
            raise HTTPException(status_code=400, detail="Invalid Subnet.")

        # Iterate to smaller subnets
        all_upper_children_subnets = await collection.find({"subnet_parent":upper_subnet_prefix}).to_list()
        for child in all_upper_children_subnets:
            child_network = ipaddress.IPv4Network(child['subnet_prefix'],strict=False)
            if child_network in list(new_subnet_network.subnets()):
                # Update child parent to the new_subnet
                await collection.update_one({"subnet_prefix":child['subnet_prefix']},{"$set":{"subnet_parent":subnet.subnet_prefix}})


        # Iterate to upper subnets towards root (if exist)
        for i in range(new_subnet_network.prefixlen-1,root_subnet_prefixlen+1,-1):
            # find the smallest upper network and set it to be a parent
            tmp_subnet_prefix = new_subnet_network.supernet(new_subnet_network.prefixlen-i)
            tmp_subnet = await collection.find_one({"subnet_prefix":str(tmp_subnet_prefix)})
            if tmp_subnet:
                upper_subnet_prefix = str(tmp_subnet_prefix)
                break

        post_data = {
            "subnet_prefix": str(new_subnet_network),
            "subnet_id": str(new_subnet_network.network_address),
            "subnet_mask": subnet.subnet_mask,
            "subnet_root": root_subnet,
            "subnet_parent": upper_subnet_prefix,
            "subnet_name": subnet.subnet_name,
            "subnet_description": subnet.subnet_description,
            "offline_utilization": 0.00,
            "online_status": "",
            "online_utilization": 0.00
        }

        await collection.insert_one(post_data)

        # Update utilization for upper subnet
        all_upper_children = await collection.find({"subnet_parent":upper_subnet_prefix}).to_list()
        all_upper_children_subnets = []
        for child in all_upper_children:
            all_upper_children_subnets.append(child['subnet_prefix'])

        utilization = get_subnet_utilization(upper_subnet_prefix,all_upper_children_subnets)
        await collection.update_one({"subnet_prefix": upper_subnet_prefix},{"$set": {"offline_utilization": utilization}})

        return {"message": "Subnet added successfully"}



# Run the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

