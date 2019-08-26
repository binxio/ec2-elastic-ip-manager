"""
AWS Auto Scaling Elastic IP manager

Manages the ip addresses associated to an auto scaling group instance.

When a lifecycle terminating event occurs, the manager will remove all the elastic ip addresses that are associated
with the instance.

When a lifecycle launching event completed successfully, the manager will add a elastic ip address with the instance. If
no elastic ips are available, it will cancel the launch event.
"""
import os
import boto3
import logging
from typing import List, Set, Optional
from .eip import EIP
from .ec2_instance import EC2Instance


from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

ec2 = boto3.client("ec2")


def get_pool_addresses(pool_name: str) -> List[EIP]:
    response = ec2.describe_addresses(
        Filters=[
            {"Name": "domain", "Values": ["vpc"]},
            {"Name": "tag:elastic-ip-manager-pool", "Values": [pool_name]},
        ]
    )
    return [EIP(a) for a in response["Addresses"]]


def describe_instance(instance_id: str) -> Optional[EC2Instance]:
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        return EC2Instance(response["Reservations"][0]["Instances"][0])
    except ClientError as e:
        log.error(f'failed to describe instance "{instance_id}", {e}')
    return None


def get_pool_instances(pool_name) -> List[EC2Instance]:
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


class Manager(object):
    def __init__(self, pool_name: str):
        self.pool_name: str = pool_name
        self.addresses: List[EIP] = []
        self.instances: List[EC2Instance] = []
        self.refresh()

    def refresh(self):
        self.addresses = get_pool_addresses(self.pool_name)
        self.instances = get_pool_instances(self.pool_name)

    def instance_addresses(self, instance_id: str) -> List[EIP]:
        return list(filter(lambda a: a.instance_id == instance_id, self.addresses))

    @property
    def available_addresses(self) -> List[EIP]:
        return list(filter(lambda a: not a.is_available, self.addresses))

    @property
    def attached_instances(self) -> Set[EC2Instance]:
        """
        all `self.instances` attached to an EIP from `self.addresses`
        """
        result = set()
        for instance in self.instances:
            if list(
                filter(lambda a: a.instance_id == instance.instance_id, self.addresses)
            ):
                result.add(instance)
        return result

    @property
    def unattached_instances(self) -> Set[str]:
        """
        all instances in the  self.instances which do not have an IP address assigned from `self.addresses`
        """
        return set(self.instances) - self.attached_instances

    def add_addresses(self):
        """
        ensure an ip address is associated with all healthy inservice asg instances.
        """
        instances = list(self.unattached_instances)
        if not instances:
            log.info(
                f'All instances in the EIP pool "{self.pool_name}" are associated with an EIP'
            )
            return

        allocation_ids = list(map(lambda a: a.allocation_id, self.available_addresses))
        if len(instances) > len(allocation_ids):
            log.warning(
                f'The Elastic IP pool "{self.pool_name}" is short of {len(instances) - len(allocation_ids)} addresses'
            )

        if not allocation_ids:
            log.error(
                f'No more IP addresses in the pool "{self.pool_name}" to assign to the instances'
            )
            return

        for instance_id, allocation_id in [
            (instances[i].instance_id, allocation_id)
            for i, allocation_id in enumerate(allocation_ids)
        ]:
            try:
                log.info(
                    f'associate ip address {allocation_id} from to "{self.pool_name}" to instance {instance_id}'
                )
                ec2.associate_address(
                    InstanceId=instance_id, AllocationId=allocation_id
                )
            except ClientError as e:
                log.error(
                    f'failed to add ip address "{allocation_id}" from "{self.pool_name}" to instance "{instance_id}", {e}'
                )

    def remove_addresses(self, instance_id: str):
        """
        disassociate all the IP addresses of the pool from the instance `self.instance_id`
        """
        if not self.instance_addresses(instance_id):
            log.info(
                f'instance "{instance_id}" but did not have an EIP from the pool associated'
            )
            return

        for allocation_id, association_id in map(
            lambda a: (a.allocation_id, a.association_id),
            self.instance_addresses(instance_id),
        ):
            try:
                log.info(
                    f'returning ip address "{allocation_id}" from instance "{instance_id}" to pool "{self.pool_name}"'
                )
                ec2.disassociate_address(AssociationId=association_id)
            except ClientError as e:
                log.error(
                    f'failed to remove elastic ip address "{allocation_id}" from instance "{instance_id}", {e}'
                )


def is_add_address_event(event):
    return (
        event.get("source") == "aws.ec2"
        and event.get("detail-type") in ["EC2 Instance State-change Notification"]
        and event.get("detail").get("state") == "running"
    )


def is_address_removed_event(event):
    return (
        event.get("source") == "aws.ec2"
        and event.get("detail-type") in ["EC2 Instance State-change Notification"]
        and event.get("detail").get("state") == "terminated"
    )


def is_timer(event) -> bool:
    return event.get("source") == "aws.events" and event.get("detail-type") in [
        "Scheduled Event"
    ]


def get_all_pool_names() -> List[str]:
    result = []
    resourcetagging = boto3.client("resourcegroupstaggingapi")
    for values in resourcetagging.get_paginator("get_tag_values").paginate(
        Key="elastic-ip-manager-pool"
    ):
        result.extend(values["TagValues"])
    return result


def handler(event: dict, context: dict):
    if is_add_address_event(event) or is_address_removed_event(event):
        instance = describe_instance(event.get("detail").get("instance-id"))
        if not instance:
            return

        if not instance.pool_name:
            log.debug(
                f'ignoring instance "{instance.instance_id}" as it is not associated with a pool'
            )
            return

        manager = Manager(instance.pool_name)
        if is_address_removed_event(event):
            manager.remove_addresses(instance.instance_id)
            manager.refresh()
        manager.add_addresses()

    elif is_timer(event):
        for pool_name in get_all_pool_names():
            manager = Manager(pool_name)
            manager.add_addresses()
    else:
        log.error(
            "ignoring event %s from source %s",
            event.get("detail-type"),
            event.get("source"),
        )
