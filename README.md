# IP Address Management (IPAM)


## Discription
A tool developed using FastAPI framework to manage IP addresses and subnets for service provider network.

The tool is used to create subnets under Major subnets of the service provider, scanning the subnets online using route lookup on service provider router (usually Route-Reflector/RR router) to gather the online status of the subnet and its utilization in live network.
Also the tool is used for reservation of the subnets by assigning a description and usage of the subnet.


## Prerequisites
- Insall Mongodb and connect using port 27017.


## Features
- Reservation of subnets.
- Provide utilization of the subnets in the tool.
- Status of the subnet in live network and its utilization.




## Installation
git clone https://github.com/EhabAOmar/IPAM.git
cd repository
