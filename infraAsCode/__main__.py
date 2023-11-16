import base64

import pulumi
import pulumi_aws as aws
import ipaddress


def calculate_subnets(vpc_cidr, num_subnets):
    try:
        vpc_network = ipaddress.IPv4Network(vpc_cidr)
    except ValueError:
        print("Invalid VPC CIDR format. Example format: 10.0.0.0/16")
        return []

    subnet_bits = vpc_network.max_prefixlen - num_subnets

    subnets = list(vpc_network.subnets(new_prefix=subnet_bits))

    return subnets


# Fetch the configuration values
config = pulumi.Config()
data = config.require_object("data")
rds_config = config.require_object("rds")
route53_config = config.require_object("route53")

# Extract key configuration values
vpc_name = data.get("vpcName")
vpc_cidr = data.get("vpcCidr")

# Create the VPC using the fetched config values
Virtual_private_cloud = aws.ec2.Vpc(vpc_name,
                                    cidr_block=vpc_cidr,
                                    instance_tenancy="default",
                                    tags={
                                        "Name": vpc_name,
                                    })

# Define availability zones
azs = aws.get_availability_zones().names
num_azs = len(azs)

no_of_subnets = data.get("no_of_subnets_AZ")  # max

print(num_azs)

if num_azs < 3:
    no_of_subnets = num_azs
# Create 3 public and 3 private subnets
public_subnets = []
private_subnets = []

subnet_cidrs = calculate_subnets(vpc_cidr, no_of_subnets * 2)

k = 0

for i in range(no_of_subnets):
    az_index = i % num_azs
    public_subnet = aws.ec2.Subnet(f"{vpc_name}-public-subnet-{i}",
                                   cidr_block=str(subnet_cidrs[k]),  # data.get(f'publicSubnetCidr{i}'),
                                   availability_zone=azs[az_index],
                                   vpc_id=Virtual_private_cloud.id,
                                   map_public_ip_on_launch=True,
                                   tags={
                                       "Name": f"{vpc_name}-public-subnet-{i}",
                                   })

    k += 1

    private_subnet = aws.ec2.Subnet(f"{vpc_name}-private-subnet-{i}",
                                    cidr_block=str(subnet_cidrs[k]),  # data.get(f'privateSubnetCidr{i}'),
                                    availability_zone=azs[az_index],
                                    vpc_id=Virtual_private_cloud.id,
                                    tags={
                                        "Name": f"{vpc_name}-private-subnet-{i}",
                                    })
    k += 1

    public_subnets.append(public_subnet)
    private_subnets.append(private_subnet)

# Create an Internet Gateway and attach it to the VPC
internet_gateway = aws.ec2.InternetGateway(f"{vpc_name}-internet-gateway",
                                           vpc_id=Virtual_private_cloud.id,
                                           tags={
                                               "Name": f"{vpc_name}-internet-gateway",
                                           })

# Create a public route table
public_route_table = aws.ec2.RouteTable(f"{vpc_name}-public-route-table",
                                        vpc_id=Virtual_private_cloud.id,
                                        tags={
                                            "Name": f"{vpc_name}-public-route-table",
                                        })

# Associate public subnets with the public route table
for subnet in public_subnets:
    aws.ec2.RouteTableAssociation(f"{subnet._name}-association",
                                  subnet_id=subnet.id,
                                  route_table_id=public_route_table.id)

# Create a private route table
private_route_table = aws.ec2.RouteTable(f"{vpc_name}-private-route-table",
                                         vpc_id=Virtual_private_cloud.id,
                                         tags={
                                             "Name": f"{vpc_name}-private-route-table",
                                         })

# Associate private subnets with the private route table
for subnet in private_subnets:
    aws.ec2.RouteTableAssociation(f"{subnet._name}-association",
                                  subnet_id=subnet.id,
                                  route_table_id=private_route_table.id)

# Create a public route in the public route table
public_route = aws.ec2.Route(f"{vpc_name}-public-route",
                             route_table_id=public_route_table.id,
                             destination_cidr_block="0.0.0.0/0",
                             gateway_id=internet_gateway.id)


def create_security_groups(vpc_id, destination_block):
    load_balancer_security_group = aws.ec2.SecurityGroup(
        "LoadBalancerSecurityGroup",
        description="Load balancer security group",
        vpc_id=vpc_id,
        ingress=[
            {
                'FromPort': 80,
                'ToPort': 80,
                'Protocol': 'tcp',
                'CidrBlocks': ["0.0.0.0/0"],
            },
            {
                'FromPort': 443,
                'ToPort': 443,
                'Protocol': 'tcp',
                'CidrBlocks': ["0.0.0.0/0"],
            },
        ],
        egress=[
            {
                'FromPort': 0,
                'ToPort': 0,
                'Protocol': '-1',
                'CidrBlocks': ["0.0.0.0/0"]
            },
        ],
    )

    application_security_group = aws.ec2.SecurityGroup(
        "AppSecurityGrp",
        description='Application security group',
        vpc_id=vpc_id,
        ingress=[
            {
                'Description': 'TLS from VPC for port 22',
                'FromPort': 22,
                'ToPort': 22,
                'Protocol': 'tcp',
                'CidrBlocks': [destination_block],
            },
            {
                'Description': 'TLS from VPC for port 8080',
                'FromPort': 8080,
                'ToPort': 8080,
                'Protocol': 'tcp',
                'security_groups': [load_balancer_security_group.id],
            },
        ],
        egress=[
            {
                'FromPort': 0,
                'ToPort': 0,
                'Protocol': '-1',
                'CidrBlocks': ["0.0.0.0/0"]
            }
        ],
    )

    database_security_group = aws.ec2.SecurityGroup(
        "DatabaseSecurityGroup",
        description="RDS security group",
        vpc_id=vpc_id,
        ingress=[
            {
                'FromPort': 5432,
                'ToPort': 5432,
                'Protocol': 'tcp',
                'security_groups': [application_security_group.id],
            },
        ],
    )

    security_group = [application_security_group, database_security_group, load_balancer_security_group]

    return security_group


def create_parameter_group():
    return (aws.rds.ParameterGroup(
        "csye6225-rds-parameter-group",
        family='postgres15',
        description='Custom parameter group for PostgresSQL'
    ))


def create_rds_instance(database_security_group):
    database_parameter_group = create_parameter_group()
    database_instance = aws.rds.Instance(
        "csye6225",
        allocated_storage=20,
        storage_type=rds_config.get("storage_type"),
        db_name=rds_config.get("db_name"),
        engine=rds_config.get("engine"),
        engine_version=rds_config.get("engine_version"),
        instance_class=rds_config.get("instance_class"),
        parameter_group_name=database_parameter_group.name,
        password=rds_config.get("password"),
        db_subnet_group_name=get_subnet_group(),
        skip_final_snapshot=True,
        username=rds_config.get("username"),
        multi_az=False,
        publicly_accessible=False,
        vpc_security_group_ids=[database_security_group],
    )
    return database_instance.address


def get_subnet_group():
    database_subnet_group = aws.rds.SubnetGroup(
        "csye6225subnetgroup",
        subnet_ids=[subnet.id for subnet in private_subnets],
    )
    return database_subnet_group.name


def lookup_ami():
    ami = aws.ec2.get_ami(
        executable_users=["self"],
        filters=[
            aws.ec2.GetAmiFilterArgs(
                name="name",
                values=["csye6225_2023_*"],
            ),
            aws.ec2.GetAmiFilterArgs(
                name="root-device-type",
                values=["ebs"],
            ),
            aws.ec2.GetAmiFilterArgs(
                name="virtualization-type",
                values=["hvm"],
            ),
        ],
        most_recent=True,
        name_regex="csye6225_2023_*",
        owners=["self"])

    return ami.id


def create_iam_role():
    # Create an IAM Role
    iam_cloudwatch_role = aws.iam.Role(
        "CloudWatch_Role",
        assume_role_policy="""{
            "Version": "2012-10-17",
            "Statement": [
                {
                "Effect": "Allow",
                "Principal": {
                    "Service": "ec2.amazonaws.com"
                },
                "Action": "sts:AssumeRole",
                "Sid": ""
                }
            ]
        }""")
    aws.iam.RolePolicyAttachment(
        "CloudWatchAgentServerPolicy",
        role=iam_cloudwatch_role.name,
        policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
    )

    instance_profile = aws.iam.InstanceProfile(
        "instance_profile",
        role=iam_cloudwatch_role.name
    )
    return instance_profile


def create_instance(ami_id, subnet_id, security_group):
    # ami_id = 'ami-011763bb2066fb36d'

    # Create the rds instance
    rds_instance = create_rds_instance(private_subnets[1], security_group[1].id)

    # with open(file=app_properties_file, mode='r') as file:
    #    static_properties = file.read()

    app_properties = '/tmp/applications.properties'

    rds_instance_hostname = pulumi.Output.concat(
        "jdbc:postgresql://",
        rds_instance,
        ":5432/",
        rds_config.get("db_name")
    )

    user_data = [
        "#!/bin/bash",
        f"echo 'spring.jpa.hibernate.ddl-auto=update' >> {app_properties}",
        f"echo 'spring.datasource.hikari.initialization-fail-timeout=-1' >> {app_properties}",
        f"echo 'spring.datasource.hikari.connection-timeout=5000' >> {app_properties}",
        f"echo 'spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.PostgreSQLDialect' >> {app_properties}",
        f"echo 'logging.level.org.springframework=debug' >> {app_properties}",
        f"echo 'spring.datasource.username={rds_config.get('username')}' >> {app_properties}",
        f"echo 'spring.datasource.password={rds_config.get('password')}' >> {app_properties}",
        f"echo 'env.domain=localhost' >> {app_properties}",
        f"echo 'env.port=8125' >> {app_properties}",
        f"echo 'management.statsd.metrics.export.host=localhost' >> {app_properties}",
        f"echo 'management.statsd.metrics.export.port=8125' >> {app_properties}",
        f"echo 'management.endpoints.web.exposure.include=metrics' >> {app_properties}",
    ]

    user_data = pulumi.Output.concat(
        "\n".join(user_data),
        "\n",
        rds_instance_hostname.apply(func=lambda x: f"echo 'spring.datasource.url={x}' >> {app_properties}"))

    user_data = pulumi.Output.concat(user_data, f"\nsudo mv {app_properties} /opt/application.properties", "\n")
    user_data = pulumi.Output.concat(user_data, "\nsudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -c file:/opt/cloudwatch.json \
    -s", "\n")

    iam_cloudwatch_role = aws.iam.Role(
        "CloudWatch_Role",
        assume_role_policy="""{
            "Version": "2012-10-17",
            "Statement": [
                {
                "Effect": "Allow",
                "Principal": {
                    "Service": "ec2.amazonaws.com"
                },
                "Action": "sts:AssumeRole",
                "Sid": ""
                }
            ]
        }""")
    aws.iam.RolePolicyAttachment(
        "CloudWatchAgentServerPolicy",
        role=iam_cloudwatch_role.name,
        policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
    )

    instance_profile = aws.iam.InstanceProfile(
        "instance_profile",
        role=iam_cloudwatch_role.name
    )

    instance = aws.ec2.Instance(
        "instance",
        ami=ami_id,
        instance_type="t2.micro",
        subnet_id=subnet_id,
        key_name="ec2",
        root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
            volume_type=data.get("root_volume_type"),
            volume_size=data.get("root_volume_size"),
            delete_on_termination=True
        ),
        disable_api_termination=False,
        vpc_security_group_ids=[security_group[0].id],
        user_data=user_data,
        iam_instance_profile=instance_profile.name,
    ),
    return instance

def create_user_data(rds_instance):
    app_properties = '/tmp/applications.properties'

    rds_instance_hostname = pulumi.Output.concat(
        "jdbc:postgresql://",
        rds_instance,
        ":5432/",
        rds_config.get("db_name")
    )

    user_data = [
        "#!/bin/bash",
        f"echo 'spring.jpa.hibernate.ddl-auto=update' >> {app_properties}",
        f"echo 'spring.datasource.hikari.initialization-fail-timeout=-1' >> {app_properties}",
        f"echo 'spring.datasource.hikari.connection-timeout=2000' >> {app_properties}",
        f"echo 'spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.PostgreSQLDialect' >> {app_properties}",
        f"echo 'logging.level.org.springframework=debug' >> {app_properties}",
        f"echo 'spring.datasource.username={rds_config.get('username')}' >> {app_properties}",
        f"echo 'spring.datasource.password={rds_config.get('password')}' >> {app_properties}",
        f"echo 'env.domain=localhost' >> {app_properties}",
        f"echo 'env.port=8125' >> {app_properties}",
        f"echo 'management.statsd.metrics.export.host=localhost' >> {app_properties}",
        f"echo 'management.statsd.metrics.export.port=8125' >> {app_properties}",
        f"echo 'management.endpoints.web.exposure.include=metrics' >> {app_properties}",
    ]

    user_data = pulumi.Output.concat(
        "\n".join(user_data),
        "\n",
        rds_instance_hostname.apply(func=lambda x: f"echo 'spring.datasource.url={x}' >> {app_properties}"))

    user_data = pulumi.Output.concat(user_data, f"\nsudo mv {app_properties} /opt/application.properties", "\n")
    user_data = pulumi.Output.concat(user_data, "\nsudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
        -a fetch-config \
        -m ec2 \
        -c file:/opt/cloudwatch.json \
        -s", "\n")
    user_data = user_data.apply(
        lambda data: base64.b64encode(data.encode()).decode())

    return user_data


def autoscaling_ec2_instances(ami_id, subnet_id, security_group, vpc_id):

    rds_instance = create_rds_instance(security_group[1].id)

    app_properties = '/tmp/applications.properties'

    rds_instance_hostname = pulumi.Output.concat(
        "jdbc:postgresql://",
        rds_instance,
        ":5432/",
        rds_config.get("db_name")
    )

    user_data = [
        "#!/bin/bash",
        f"echo 'spring.jpa.hibernate.ddl-auto=update' >> {app_properties}",
        f"echo 'spring.datasource.hikari.initialization-fail-timeout=-1' >> {app_properties}",
        f"echo 'spring.datasource.hikari.connection-timeout=2000' >> {app_properties}",
        f"echo 'spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.PostgreSQLDialect' >> {app_properties}",
        f"echo 'logging.level.org.springframework=debug' >> {app_properties}",
        f"echo 'spring.datasource.username={rds_config.get('username')}' >> {app_properties}",
        f"echo 'spring.datasource.password={rds_config.get('password')}' >> {app_properties}",
        f"echo 'env.domain=localhost' >> {app_properties}",
        f"echo 'env.port=8125' >> {app_properties}",
        f"echo 'management.statsd.metrics.export.host=localhost' >> {app_properties}",
        f"echo 'management.statsd.metrics.export.port=8125' >> {app_properties}",
        f"echo 'management.endpoints.web.exposure.include=metrics' >> {app_properties}",
    ]

    user_data = pulumi.Output.concat(
        "\n".join(user_data),
        "\n",
        rds_instance_hostname.apply(func=lambda x: f"echo 'spring.datasource.url={x}' >> {app_properties}"))

    user_data = pulumi.Output.concat(user_data, f"\nsudo mv {app_properties} /opt/application.properties", "\n")
    user_data = pulumi.Output.concat(user_data, "\nsudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
        -a fetch-config \
        -m ec2 \
        -c file:/opt/cloudwatch.json \
        -s", "\n")
    user_data = user_data.apply(
        lambda data: base64.b64encode(data.encode()).decode())

    # Create an IAM Role
    iam_cloudwatch_role = aws.iam.Role(
        "CloudWatch_Role",
        assume_role_policy="""{
            "Version": "2012-10-17",
            "Statement": [
                {
                "Effect": "Allow",
                "Principal": {
                    "Service": "ec2.amazonaws.com"
                },
                "Action": "sts:AssumeRole",
                "Sid": ""
                }
            ]
        }""")
    aws.iam.RolePolicyAttachment(
        "CloudWatchAgentServerPolicy",
        role=iam_cloudwatch_role.name,
        policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
    )

    instance_profile = aws.iam.InstanceProfile(
        "instance_profile",
        role=iam_cloudwatch_role.name
    )

    launch_template = aws.ec2.LaunchTemplate(
        "AutoscalingLaunchConfig",
        image_id=ami_id,
        instance_type="t2.micro",
        key_name="ec2",
        user_data=user_data,
        iam_instance_profile=aws.ec2.LaunchTemplateIamInstanceProfileArgs(
            name=instance_profile.name,
        ),
        block_device_mappings=[{  # Array of mappings
            "device_name": "/dev/xvda",  # Device name
            "ebs": {
                "volume_size": data.get("root_volume_size"),
                "volume_type": data.get("root_volume_type"),
                "delete_on_termination": True  # Terminate EBS volume on instance termination
            },
        }],
        network_interfaces=[
            aws.ec2.LaunchTemplateNetworkInterfaceArgs(
                associate_public_ip_address=True,
                security_groups=[security_group[0].id],
                subnet_id=public_subnets[0],
            ),
        ],
        disable_api_termination=False,
    )

    target_group = aws.lb.TargetGroup(
        "webapp-target-group",
        port=8080,
        slow_start=30,
        health_check=aws.lb.TargetGroupHealthCheckArgs(
            path="/healthz",
            port=8080,
            matcher=200,
            healthy_threshold=3,
            unhealthy_threshold=3,
            protocol="HTTP",
            interval=10,
        ),
        protocol="HTTP",
        target_type="instance",
        vpc_id=vpc_id,
    )

    autoscaling_group = aws.autoscaling.Group(
        "AutoscalingGroup",
        min_size=1,
        max_size=3,
        desired_capacity=1,
        default_cooldown=60,
        default_instance_warmup=10,
        health_check_type="ELB",
        target_group_arns=[target_group.arn],
        launch_template=aws.autoscaling.GroupLaunchTemplateArgs(
            id=launch_template.id,
            version="$Latest",
        ),
        vpc_zone_identifiers=[subnet.id for subnet in public_subnets],
        health_check_grace_period=300,
        tags=[
            aws.autoscaling.GroupTagArgs(
                key='Name',
                value='ASGInstance',
                propagate_at_launch=True,
            )
        ],
    )

    autoscaling_up_policy = aws.autoscaling.Policy(
        "AutoScalingPolicyUp1",
        adjustment_type="ChangeInCapacity",
        policy_type="SimpleScaling",
        autoscaling_group_name=autoscaling_group.name,
        scaling_adjustment=1,
        metric_aggregation_type="Average",
    )

    autoscaling_down_policy = aws.autoscaling.Policy(
        "AutoScalingPolicyDown1",
        adjustment_type="ChangeInCapacity",
        policy_type="SimpleScaling",
        autoscaling_group_name=autoscaling_group.name,
        scaling_adjustment=-1,
        metric_aggregation_type="Average",
    )

    # Create a CloudWatch metric alarm for scaling up.
    scaling_up_alarm = aws.cloudwatch.MetricAlarm(
        "ScalingUpAlarm",
        comparison_operator="GreaterThanOrEqualToThreshold",
        evaluation_periods=2,
        metric_name="CPUUtilization",
        namespace="AWS/EC2",
        period=60,
        statistic="Average",
        threshold="5",
        alarm_actions=[autoscaling_up_policy.arn],
        dimensions={
            "AutoScalingGroupName": autoscaling_group.name,
        },
    )

    scaling_down_alarm = aws.cloudwatch.MetricAlarm(
        "ScalingDownAlarm",
        comparison_operator="LessThanOrEqualToThreshold",
        evaluation_periods=1,
        metric_name="CPUUtilization",
        namespace="AWS/EC2",
        period=60,
        statistic="Average",
        threshold="3",
        alarm_actions=[autoscaling_down_policy.arn],
        dimensions={
            "AutoScalingGroupName": autoscaling_group.name,
        },
    )

    load_balancer = aws.lb.LoadBalancer(
        "webapp-alb",
        load_balancer_type="application",
        security_groups=[security_group[2].id],
        enable_deletion_protection=False,
        internal=False,
        subnets=[subnets.id for subnets in public_subnets],
    )

    listener = aws.lb.Listener(
        "webapp-listener",
        default_actions=[
            aws.lb.ListenerDefaultActionArgs(
                type="forward",
                target_group_arn=target_group.arn,
            )],
        load_balancer_arn=load_balancer.arn,
        port=80,
        protocol="HTTP",
    )
    return load_balancer


def update_record_in_route53(lb):
    my_zone = aws.route53.get_zone(name=route53_config.get("name"))
    record = aws.route53.Record(
        "route53_record",
        type="A",
        name=my_zone.name,
        aliases=[aws.route53.RecordAliasArgs(
            name=lb.dns_name,
            zone_id=lb.zone_id,
            evaluate_target_health=True,
        )],
        zone_id=my_zone.zone_id
    )
    return record


def demo():
    vpc_id = Virtual_private_cloud.id
    destination_block = '0.0.0.0/0'

    # Create the security group.
    security_group = create_security_groups(vpc_id, destination_block)

    # Create the EC2 instance.
    # instance = create_instance(data.get("ami_id"), public_subnets[0], security_group)

    load_balancer = autoscaling_ec2_instances(data.get("ami_id"), public_subnets[0], security_group, vpc_id)
    update_record_in_route53(load_balancer)


demo()
