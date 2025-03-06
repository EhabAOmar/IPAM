from fastapi import FastAPI, HTTPException, Request, Query
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from typing import List, Optional
from fastapi.staticfiles import StaticFiles
import ipaddress
from utils import route_scan, router_connection_test, get_subnet_utilization, validate_ip, validate_prefix_length

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

# Pydantic model for validation
class Subnet(BaseModel):
    subnet_prefix: str = Field(...)
    subnet_id: str = Field(...)
    subnet_mask: str = Field(...)
    subnet_root: str = None
    subnet_parent: str = None
    subnet_name: str = Field(...)
    subnet_service: str = Field(...)
    offline_utilization: float = 0.00
    online_status: str = ""
    online_utilization: float = 0.00

class Router(BaseModel):
    router_ip: str = Field(...)
    router_name: str = Field(...)
    router_username: str = Field(...)
    router_password: str = Field(...)
    router_vendor: str = Field(...)



@app.get("/")
async def serve_index(request: Request):
    subnets = await collection.find().to_list()
    major_subnets = [subnet for subnet in subnets if subnet['subnet_prefix'] == subnet['subnet_root']]
    return templates.TemplateResponse("index.html", {"request": request, "subnets": major_subnets})





@app.get("/routers")
async def list_routers(request: Request):
    routers = await router_collection.find().to_list(length=100)

    if not routers:
        return {"error": "Router not found"}
    for router in routers:
        router["_id"] = str(router["_id"])  # Convert ObjectId to string

    return templates.TemplateResponse("router_detail.html", {"request": request, "routers": routers})


@app.get("/add-router")
async def add_router_page(request: Request):
    return templates.TemplateResponse("add_router.html", {"request": request})



# Add a new router
@app.post("/routers/")
async def add_router(router: Router):
    existing_router = await router_collection.find_one({
        "router_ip": router.router_ip
    })
    if existing_router:
        raise HTTPException(status_code=400, detail="Router already exists")

    # Limit is 2 routers, one is main and other is backup
    all_existing_routers = await router_collection.find().to_list()
    if len(all_existing_routers) == 2:
        raise HTTPException(status_code=400, detail="Limit exceeded, there are two Routers.")

    router_dict = router.model_dump()
    await router_collection.insert_one(router_dict)
    return {"message": "Router added successfully"}


# Update Router
@app.put("/routers/{router_id}")
async def update_router(router_id: str, updateData: dict):
    object_id = ObjectId(router_id)  # Convert to ObjectId
    router = await router_collection.find_one({"_id": object_id})


    if not router:
        raise HTTPException(status_code=404, detail="Router not found")

    update_data = {
        "router_name": updateData['router_name'],
        "router_username": updateData['router_username'],
        "router_password": updateData['router_password'],
        "router_vendor": updateData['router_vendor']
    }

    await router_collection.update_one({"_id": router["_id"]},{"$set": update_data})
    return {"success": True}



# Delete Router by ObjectId
@app.delete("/routers/{router_id}")
async def delete_router(router_id: str):
    object_id = ObjectId(router_id)   # Convert to ObjectId
    result = await router_collection.delete_one({"_id": object_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Router not found")

    return {"message": f"Router Deleted Successfully"}



# Test router connection
@app.get("/routers/testconnection/{router_id}")
async def testConnection(router_id: str):
    object_id = ObjectId(router_id)   # Convert to ObjectId
    router = await router_collection.find_one({"_id": object_id})

    device_info = {"hostname": router['router_ip'], "username": router['router_username'], "password": router['router_password'] }

    # Test if SSH to router is successful using the input username and password
    result = router_connection_test(router['router_vendor'], **device_info)

    if result:
        return {"message": "Test Connection success"}
    else:
        return {"message": "Test Connection Failed"}






# Add Major subnet page
@app.get("/add-major-subnet")
async def add_subnet_page(request: Request):
    return templates.TemplateResponse("add_major_subnet.html", {"request": request})



# Major subnet detail page
@app.get("/subnets/{subnet_id}-{subnet_mask}")
async def get_major_subnet_detail(request: Request, subnet_id: str, subnet_mask: str):
    major_subnet_prefix = f"{subnet_id}/{subnet_mask}"
    major_subnet = await collection.find_one({"subnet_prefix": major_subnet_prefix })

    if not major_subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    # Get all active subnets under the selected major subnet
    all_subnets = await collection.find({"subnet_parent":major_subnet_prefix}).to_list()

    for subnet in all_subnets:
        subnet["_id"] = str(subnet["_id"])  # Convert ObjectId to string
    return templates.TemplateResponse("subnet_detail.html", {"request": request, "subnet": major_subnet, "subnets": all_subnets})



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
async def delete_subnets(subnet_ids: List[str]):

    # Delete the subnet only if it has no child subnets
    for subnet_id in subnet_ids:
        object_id = ObjectId(subnet_id)
        subnet = await collection.find_one({"_id": object_id})
        subnet_prefix = subnet['subnet_prefix']
        child_subnets = await collection.find({"subnet_parent":subnet_prefix}).to_list()

        if child_subnets:
            subnet_ids.remove(subnet_id)
            raise HTTPException(status_code=400, detail="The subnet contains active smaller subnet(s). Cant' be deleted!")

    if subnet_ids:
        object_ids = [ObjectId(subnet_id) for subnet_id in subnet_ids]  # Convert to ObjectId

        upper_subnet_prefixes = []

        for object_id in object_ids:
            subnet = await collection.find_one({"_id": object_id})
            upper_subnet_prefixes.append(subnet['subnet_parent'])

        result = await collection.delete_many({"_id": {"$in": object_ids}})

        if result.deleted_count == 0:
            raise HTTPException(status_code=400, detail="The subnet contains active smaller subnet(s). Cant' be deleted!")


        # Update utilization for upper subnet
        for upper_subnet_prefix in upper_subnet_prefixes:
            all_upper_children = await collection.find({"subnet_parent": upper_subnet_prefix}).to_list()
            all_upper_children_subnets = []
            for child in all_upper_children:
                all_upper_children_subnets.append(child['subnet_prefix'])

            utilization = get_subnet_utilization(upper_subnet_prefix,all_upper_children_subnets)
            utilization_result = await collection.update_one({"subnet_prefix": upper_subnet_prefix},{"$set": {"offline_utilization": utilization}})


        return {"message": f"Deleted {result.deleted_count} subnets"}



# Update a subnet
@app.put("/subnets/{subnet_id}")
async def update_subnet(subnet_id: str, updateData: dict):

    object_id = ObjectId(subnet_id)  # Convert to ObjectId
    existing_subnet = await collection.find_one({"_id": object_id})


    # subnet_prefix = f"{subnet_id}/{subnet_mask}"
    # existing_subnet = await collection.find_one({"subnet_prefix": subnet_prefix})

    subnet_name = updateData["subnet_name"]
    subnet_service = updateData["subnet_service"]


    if not existing_subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    update_data = {
        "subnet_name": subnet_name,
        "subnet_service": subnet_service,
    }

    await collection.update_one({"_id": existing_subnet["_id"]},{"$set": update_data})

    return {"success": True}
    # return {"message": "Subnet updated successfully"}



# Scan a subnet
@app.put("/scan_subnet/{subnet_id}-{subnet_mask}")
async def scan_subnet(data: dict):
    subnet_prefix= data['subnet_prefix']
    existing_subnet = await collection.find_one({"subnet_prefix": subnet_prefix})

    if not existing_subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    routers = await router_collection.find().to_list()   #return the two routers

    if not routers:
        return {"message": "Router not found, please add router first to scan online"}

    router = routers[0]
    router_vendor = router['router_vendor']
    device_info = {"hostname": router['router_ip'], "username": router['router_username'], "password": router['router_password'] }

    # If connection failed to the main router, proceed to the backup router if exists.
    if (not router_connection_test(router_vendor, **device_info)) and routers[1]:
        router = routers[1]
        router_vendor = router['router_vendor']
        device_info = {"hostname": router['router_ip'], "username": router['router_username'], "password": router['router_password'] }


    scan_result = route_scan(subnet_prefix, router_vendor, **device_info)

    # If route successfully was queried from the router, then update the scan results with online status and utilization.
    if scan_result['status']:
        update_data = {
            "online_status": scan_result['online_status'],
            "online_utilization": scan_result['online_utilization']
        }

        await collection.update_one(
            {"_id": existing_subnet["_id"]},  # Using MongoDB's `_id` to ensure correct document
            {"$set": update_data}
        )

        return {"message": "Subnet Scanned Successfully"}

    return {"message": "Connection to Router Failed"}



# Get subnet information under Major subnet
@app.get("/subnets/{major_subnet_id}-{major_subnet_mask}/add-subnet")
async def add_subnet_form(request: Request, major_subnet_id: str, major_subnet_mask: str):
    return templates.TemplateResponse("add_subnet.html", {"request": request,"major_subnet_id": major_subnet_id, "major_subnet_mask": major_subnet_mask})



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

    # Subnet already exists. Display a message.
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
                result = await collection.update_one({"subnet_prefix":child['subnet_prefix']},{"$set":{"subnet_parent":subnet.subnet_prefix}})


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
            "subnet_service": subnet.subnet_service,
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
        result = await collection.update_one({"subnet_prefix": upper_subnet_prefix},{"$set": {"offline_utilization": utilization}})

        return {"message": "Subnet added successfully"}



# Run the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

