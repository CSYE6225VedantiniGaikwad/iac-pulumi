import pulumi
import pulumi_aws as aws
import ipaddress

def calSubnets(vpcCidr, numSubnets):
    try:
        vpcNetwork = ipaddress.IPv4Network(vpcCidr)
    except ValueError:
        print("Invalid VPC CIDR format. Example format: 10.0.0.0/16")
        return []

    subnetBits = vpcNetwork.max_prefixlen - numSubnets

    subnets = list(vpcNetwork.subnets(new_prefix=subnetBits))
    
    return subnets


config = pulumi.Config()
data = config.require_object("data")


vpcName = data.get("vpcName")
vpcCidr = data.get("vpcCidr")

VirtualPrivateCloud = aws.ec2.Vpc(vpcName,
    cidr_block=vpcCidr,
    instance_tenancy="default",
    tags={
        "Name": vpcName,
    })


azs = aws.get_availability_zones().names
numAzs = len(azs)

noOfSubnets = 3 # max

print(numAzs)

if (numAzs < 3):
    noOfSubnets = numAzs

publicSubnets = []
privateSubnets = []

subnetCidrs = calSubnets(vpcCidr, noOfSubnets * 2)

k = 0

for i in range(noOfSubnets):
    azIndex = i % numAzs
    publicSubnet = aws.ec2.Subnet(f"{vpcName}-public-subnet-{i}",
        cidr_block= str(subnetCidrs[k]), #data.get(f'publicSubnetCidr{i}'),
        availability_zone=azs[azIndex],
        vpc_id = VirtualPrivateCloud.id,
        map_public_ip_on_launch=True,
        tags={
            "Name": f"{vpcName}-public-subnet-{i}",
        })

    k += 1

    privateSubnet = aws.ec2.Subnet(f"{vpcName}-private-subnet-{i}",
        cidr_block= str(subnetCidrs[k]), #data.get(f'privateSubnetCidr{i}'),
        availability_zone=azs[azIndex],
        vpc_id=VirtualPrivateCloud.id,
        tags={
            "Name": f"{vpcName}-private-subnet-{i}",
        })
    k += 1

    publicSubnets.append(publicSubnet)
    privateSubnets.append(privateSubnet)

# Create an Internet Gateway and attach it to the VPC
internet_gateway = aws.ec2.InternetGateway(f"{vpcName}-internet-gateway",
    vpc_id=VirtualPrivateCloud.id,
    tags={
        "Name": f"{vpcName}-internet-gateway",
    })

 

# Create a public route table
public_route_table = aws.ec2.RouteTable(f"{vpcName}-public-route-table",
    vpc_id=VirtualPrivateCloud.id,
    tags={
        "Name": f"{vpcName}-public-route-table",
    })

 

# Associate public subnets with the public route table
for subnet in publicSubnets:
    aws.ec2.RouteTableAssociation(f"{subnet._name}-association",
        subnet_id=subnet.id,
        route_table_id=public_route_table.id)

 

# Create a private route table
private_route_table = aws.ec2.RouteTable(f"{vpcName}-private-route-table",
    vpc_id=VirtualPrivateCloud.id,
    tags={
        "Name": f"{vpcName}-private-route-table",
    })

 

# Associate private subnets with the private route table
for subnet in privateSubnets:
    aws.ec2.RouteTableAssociation(f"{subnet._name}-association",
        subnet_id=subnet.id,
        route_table_id=private_route_table.id)

# Create a public route in the public route table
public_route = aws.ec2.Route(f"{vpcName}-public-route",
    route_table_id=public_route_table.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=internet_gateway.id)

# pdb.set_trace()