import logging
import os
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

ec2 = boto3.client("ec2")


class EC2Instance(dict):
    def __init__(self, instance: dict):
        self.update(instance)

    @property
    def instance_id(self) -> str:
        return self["InstanceId"]

    @property
    def primary_network_interface_id(self):
        return self["NetworkInterfaces"][0]["NetworkInterfaceId"] if self["NetworkInterfaces"] else None

    @property
    def pool_name(self) -> str:
        return self.tags.get("elastic-ip-manager-pool", None)

    @property
    def tags(self) -> dict:
        return {t["Key"]: t["Value"] for t in self["Tags"]}

    def __key(self):
        return self["InstanceId"]

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, other):
        return self.__key() == other.__key()

    def __str__(self):
        return str(self.__key())


def describe_pool_instance(instance_id: str) -> Optional[EC2Instance]:
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        return EC2Instance(response["Reservations"][0]["Instances"][0])
    except ClientError as e:
        log.error(f'failed to describe instance "{instance_id}", {e}')
    return None


def get_pool_instances(pool_name: str) -> List[EC2Instance]:
    """
    get all running ec2 instances with tagged elastic-ip-manager-pool with `pool_name`
    """
    result = []
    for response in ec2.get_paginator("describe_instances").paginate(
        Filters=[
            {"Name": "tag:elastic-ip-manager-pool", "Values": [pool_name]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    ):
        for reservation in response["Reservations"]:
            result.extend([EC2Instance(i) for i in reservation["Instances"]])
    return result
