# IP Address Management (IPAM)


## Discription
A web application developed using FastAPI framework to manage IP subnets for service provider network.

The application is used to create subnets under Major subnets of the service provider, scanning the subnets online using route lookup on service provider router (usually Route-Reflector/RR router) to gather the online status of the subnet and its utilization in live network.
Also the application is used for reservation of the subnets by assigning a description and usage of the subnet.


## Prerequisites
- Insall Mongodb and connect using default port 27017.
- Set "SECRET_KEY" as environment variable in OS to be used as a master key for user password encryption and decryption. You may use any other method preferred to retreive the "SECRET_KEY" for encryption/decryption.


## Features
- Web GUI for subnets management and reservation.
- Utilization of the subnets inside the tool.
- Status of the subnets in live network and its actual/online utilization.
- Search subnet in the database.



![Alt text](static/Home-Page1.png)

## Installation
git clone https://github.com/EhabAOmar/IPAM.git
cd repository
