# iac-pulumi #

This project demonstrates the creation of a Virtual Private Cloud (VPC) along with the necessary resources such as subnets, an Internet Gateway, and route tables using infrastructure as code (IaC) tools.

## Table of Contents ##
* Introduction
* Prerequisites
* Getting Started
* Deployment

#### Introduction ####
This project automates the creation of a VPC with a specific configuration that includes:

1. Creating a VPC in a specified region.
2. Creating three public subnets and three private subnets, each distributed across different availability zones within the same region.
3. Attaching an Internet Gateway to the VPC for public internet access.
4. Creating separate route tables for public and private subnets.
5. Associating public subnets with the public route table.
6. Adding a default route for the public route table to route internet-bound traffic via the Internet Gateway.

### Prerequisites ###
Before getting started, ensure you have the following prerequisites:

1. Pulumi installed on your local machine.
2. AWS account credentials configured with the necessary permissions for VPC and related resources.
3. Basic knowledge of Pulumi and AWS services.

### Getting Started ###
Follow these steps to set up and deploy the project:

1. Clone this repository to your local machine.
2. Configure your AWS credentials using environment variables or AWS configuration files.
3. Review the project configuration to customize settings (if necessary).
4. Deploy the project using Pulumi.

### Deployment ###
Use the following commands to deploy the project:

#### Using pulumi ####
    pulumi up

Follow the prompts to confirm and apply the changes. The infrastructure will be created based on the defined configuration.

### Destroy Resources ###
Use the following commands to destroy all resources that are created on a stack:

#### Using pulumi ####
    pulumi destroy

#### Command to import certificate into AWS Certificate Manager ####
    aws acm import-certificate --profile demo01 --certificate fileb://demo_vedantinigaikwad_me.crt --private-key fileb://"C:\Program Files\OpenSSL-Win64\bin\private.key"