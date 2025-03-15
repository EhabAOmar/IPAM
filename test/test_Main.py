import pytest
from fastapi.testclient import TestClient
from Main import app
from unittest.mock import AsyncMock, patch
from bson import ObjectId


client = TestClient(app)



#####################################################################
# Defining Fixtures

@pytest.fixture
def mock_mongo_router():
    """Mock MongoDB collection"""
    with patch("Main.router_collection") as mock_router_collection:
        mock_router_collection.find_one = AsyncMock(return_value=None)  # No existing router

        async_mock_find = AsyncMock()
        async_mock_find.to_list = AsyncMock(return_value=[])  # Return an empty list
        mock_router_collection.find.return_value = async_mock_find  # Assign mocked `find()`

        mock_router_collection.update_one = AsyncMock(return_value=None)
        mock_router_collection.insert_one = AsyncMock(return_value=None)  # Mock insert
        mock_router_collection.delete_one = AsyncMock(return_value=AsyncMock(deleted_count=1))  # Mock delete

        yield mock_router_collection  # Provide the mock to tests



@pytest.fixture
def mock_mongo_subnet():
    """Mock MongoDB collection"""
    with patch("Main.collection") as mock_subnet_collection:
        mock_subnet_collection.find_one = AsyncMock(return_value=None)  # No existing router

        async_mock_find = AsyncMock()
        async_mock_find.to_list = AsyncMock(return_value=[])  # Return an empty list
        mock_subnet_collection.find.return_value = async_mock_find  # Assign mocked `find()`

        mock_subnet_collection.update_one = AsyncMock(return_value=None)
        mock_subnet_collection.insert_one = AsyncMock(return_value=None)  # Mock insert
        mock_subnet_collection.delete_one = AsyncMock(return_value=AsyncMock(deleted_count=1))  # Mock delete
        mock_subnet_collection.delete_many = AsyncMock(return_value=AsyncMock(deleted_count=1))  # Mock delete Many
        yield mock_subnet_collection  # Provide the mock to tests



@pytest.fixture
def mock_router_connection_test():
    with patch("Main.router_connection_test") as mock:
        yield mock

@pytest.fixture
def mock_route_scan():
    with patch("Main.route_scan") as mock:
        yield mock


################################################################################################
# Defining Data


router_id = str(ObjectId()) 


router_data_valid = {
    "router_ip": "192.168.1.1",
    "router_name": "test_router",
    "router_username": "test_username",
    "router_password": "test_password",
    "router_vendor": "Juniper"
}


router_data_invalid = {
    "router_ip": "192.168",
    "router_name": "test_router",
    "router_username": "test_username",
    "router_password": "test_password",
    "router_vendor": "Juniper"
}

router1_data_valid = {
    "router_ip": "192.168.2.1",
    "router_name": "test_router1",
    "router_username": "test_username",
    "router_password": "test_password",
    "router_vendor": "Juniper"
}

router2_data_valid = {
    "router_ip": "192.168.2.2",
    "router_name": "test_router2",
    "router_username": "test_username",
    "router_password": "test_password",
    "router_vendor": "Juniper"
}

update_router_data = {
    "router_name": "UpdatedRouter",
    "router_password": "newpassword"
}


moc_id = ObjectId()

subnet_dict = {"subnet_prefix": "192.168.1.0/24",
                   "subnet_id": "_subnet_id",
                   "subnet_mask": "24",
                   "subnet_root": "192.168.1.0/24",
                   "subnet_parent": "",
                   "subnet_name": "test",
                   "subnet_service": "test",
                   "subnet_description": "test",
                   "offline_utilization": 0.00,
                   "online_status": "",
                   "online_utilization": 0.00
                   }

moc_mongo_subnet_dict = {"_id": "moc_id",
                    "subnet_prefix": "192.168.1.0/24",
                   "subnet_id": "_subnet_id",
                   "subnet_mask": "24",
                   "subnet_root": "192.168.1.0/24",
                   "subnet_parent": "",
                   "subnet_name": "test",
                   "subnet_service": "test",
                   "subnet_description": "test",
                   "offline_utilization": 0.00,
                   "online_status": "",
                   "online_utilization": 0.00
                   }

################################################################################################
# ✅ Testing Main Page
def test_read_root():
    response = client.get("/")
    assert response.status_code == 200

################################################################################################
# Testing Routers


# ✅ Test: Add New Router Page
def test_get_add_router():
    response = client.get("/add-router")
    assert response.status_code == 200


# ✅ Test: Adding Router Success
def test_add_router_success(mock_mongo_router):
    response = client.post("/routers/", json=router_data_valid)
    assert response.status_code == 200
    assert response.json() == {"message": "Router added successfully"}


# ✅ Test: Added New Router Already Exist
def test_add_router_existing_ip(mock_mongo_router):
    mock_mongo_router.find_one.return_value = [router_data_valid]  # Simulate existing router
    response = client.post("/routers/", json=router_data_valid)
    assert response.status_code == 400
    assert response.json()["detail"] == "Router already exists"


# ✅ Test: Add More than Routers Number Limit
def test_add_router_limit_exceeded(mock_mongo_router):
    #Test adding a third router when limit is 2
    async_mock_find = AsyncMock()
    async_mock_find.to_list = AsyncMock(return_value=[router1_data_valid, router2_data_valid])  # Two routers exist
    mock_mongo_router.find.return_value = async_mock_find

    response = client.post("/routers/", json=router_data_valid)
    assert response.status_code == 400
    assert response.json()["detail"] == "Limit exceeded, there are already two Routers."


# ✅ Test: Router Input IP Invalid
def test_add_router_invalid_ip():
    response = client.post("/routers/", json=router_data_invalid)
    assert response.status_code == 400
    assert response.json()["detail"] == "Wrong Router IP."


# ✅ Test: Update Router Successfully
def test_update_router_success(mock_mongo_router):
    mock_mongo_router.find_one.return_value = {"_id": ObjectId(router_id), **router_data_valid}  # Existing router

    response = client.put(f"/routers/{router_id}", json=update_router_data)
    assert response.status_code == 200
    assert response.json() == {"success": True}


# ✅ Test: Update Router Not Found
def test_update_router_not_found(mock_mongo_router):
    mock_mongo_router.find_one.return_value = None  # No router found

    response = client.put(f"/routers/{router_id}", json=update_router_data)
    assert response.status_code == 404
    assert response.json()["detail"] == "Router not found"


# ✅ Test: Delete Router Successfully
def test_delete_router_success(mock_mongo_router):
    mock_mongo_router.find_one.return_value = {"_id": ObjectId(router_id), **router_data_valid}  # Router exists

    response = client.delete(f"/routers/{router_id}")
    assert response.status_code == 200
    assert response.json() == {"message": "Router Deleted Successfully"}


# ✅ Test: Delete Non-Existing Router
def test_delete_router_not_found(mock_mongo_router):
    mock_mongo_router.delete_one.return_value = AsyncMock(deleted_count=0)  # Simulate no deletion

    response = client.delete(f"/routers/{router_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Router not found"


################################################################################################
# Testing Subnets


# ✅ Test: Add Major Subnet Page
def test_get_add_major_subnet():
    response = client.get("/add-major-subnet")
    assert response.status_code == 200


# ✅ Test: Subnet Detail Page
def test_get_subnet_detail_success(mock_mongo_subnet):
    mock_subnet = {"subnet_prefix": "192.168.1.0/24", "subnet_mask": "24", "_id": "moc_id"}
    mock_subnets = [
        {"subnet_prefix": "192.168.1.0/25", "subnet_mask": "25", "_id": "subnet1"},
        {"subnet_prefix": "192.168.1.128/25", "subnet_mask": "25", "_id": "subnet2"}
    ]

    mock_mongo_subnet.find_one.return_value = mock_subnet
    mock_mongo_subnet.find.return_value.to_list.return_value = mock_subnets

    response = client.get("/subnets/192.168.1.0-24")

    assert response.status_code == 200
    assert "192.168.1.0/24" in response.text



# ✅ Test: Subnet Doesn't Exist
def test_get_subnet_detail_not_existing(mock_mongo_subnet):
    mock_mongo_subnet.find_one.return_value = None

    response = client.get("/subnets/192.168.1.0-24")

    assert response.status_code == 404
    assert response.json() == {"detail": "Subnet not found"}


# ✅ Test: Add Major Subnet Successfully
def test_add_major_subnet_success(mock_mongo_subnet):
    mock_mongo_subnet.find_one.return_value = None  # No existing subnet

    response = client.post("/subnets/", json=subnet_dict)

    assert response.status_code == 200
    assert response.json() == {"message": "Subnet added successfully"}


# ✅ Test: The New Added Major Subnet Already Exist
def test_add_major_subnet_already_exists(mock_mongo_subnet):
    mock_mongo_subnet.find_one.return_value = {"subnet_prefix": "192.168.1.0/24"}

    response = client.post("/subnets/", json=subnet_dict)

    assert response.status_code == 400
    assert response.json() == {"detail": "Major Subnet already exists"}


# ✅ Test: Delete Subnet Successfully
def test_delete_subnet_success(mock_mongo_subnet):
    mock_mongo_subnet.find_one.return_value = {"_id": moc_id, "subnet_prefix": "192.168.1.0/24", "subnet_parent":""}  # Found subnet

    mock_mongo_subnet.delete_many.return_value.deleted_count = 1

    response = client.delete(f"/subnet/{moc_id}")
    assert response.status_code == 200
    assert response.json() == {"message": "Subnet Deleted"}


# ✅ Test: Delete Subnet with Children Subnet
def test_delete_subnet_with_children(mock_mongo_subnet):
    child_id = ObjectId()
    mock_mongo_subnet.find_one.return_value = {"_id": moc_id, "subnet_prefix": "192.168.1.0/24", "subnet_parent":""}  # Found subnet

    mock_mongo_subnet.find.return_value.to_list = AsyncMock(return_value=[{"_id": child_id, "subnet_prefix": "192.168.1.0/25", "subnet_parent": "192.168.1.0/24"}])

    response = client.delete(f"/subnet/{moc_id}")

    assert response.status_code == 400
    assert response.json() == {"detail": "The subnet contains active smaller subnet(s). Cant' be deleted!"}


# ✅ Test: Delete Subnet Successfully (no Children Subnets)
def test_update_subnet_success(mock_mongo_subnet):
    mock_mongo_subnet.find_one.return_value = {"_id": moc_id}

    response = client.put(f"/subnets/{moc_id}", json={"subnet_name": "Updated Name"})

    assert response.status_code == 200
    assert response.json() == {"success": True}


# ✅ Test: Update Subnet Not Found
def test_update_subnet_not_found(mock_mongo_subnet):
    mock_mongo_subnet.find_one.return_value = None
    response = client.put(f"/subnets/{moc_id}", json={"subnet_name": "Updated Name"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Subnet not found"}

# ✅ Test: Scan Subnet Successfully
def test_scan_subnet_success(mock_mongo_subnet,mock_mongo_router,mock_router_connection_test,mock_route_scan):
    mock_mongo_subnet.find_one.return_value = {"_id": moc_id, "subnet_prefix": "192.168.1.0/24"}

    async_mock_find = AsyncMock()
    async_mock_find.to_list = AsyncMock(return_value=[router1_data_valid, router2_data_valid])  # Two routers exist
    mock_mongo_router.find.return_value = async_mock_find

    mock_router_connection_test.return_value = True
    mock_route_scan.return_value = {"status": True, "online_status": "Active", "online_utilization": 0.0}

    subnet_dict = {"subnet_prefix": "192.168.1.0/24"}

    response = client.put("/scan_subnet/", json=subnet_dict)

    assert response.status_code == 200
    assert response.json() == {"message": "Subnet Scanned Successfully"}


# ✅ Test: Scan Subnet Not Found
def test_scan_subnet_not_found(mock_mongo_subnet):
    mock_mongo_subnet.find_one.return_value = None

    response = client.put("/scan_subnet/", json=subnet_dict)

    assert response.status_code == 404
    assert response.json() == {"detail": "Subnet not found"}

