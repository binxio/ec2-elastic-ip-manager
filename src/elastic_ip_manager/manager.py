"""
AWS Auto Scaling Elastic IP manager

Manages Elastic IP addresses associated to ec2 instances.

When a instances is stopped or terminated, the manager will remove all the EIPs that are associated
with the instance.

When a instance is started, the manager will add an Elastic IP address to the instance.
"""
import os
import boto3
import logging
from typing import List, Set, Optional
from .eip import EIP, get_pool_addresses
from .ec2_instance import EC2Instance, get_pool_instances, describe_pool_instance

from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
ec2 = boto3.client("ec2")
cloudwatch = boto3.client("cloudwatch")


class Manager(object):
    def __init__(self, pool_name: str):
        self.pool_name: str = pool_name
        self.addresses: List[EIP] = []
        self.instances: List[EC2Instance] = []

    def refresh(self):
        self.addresses = get_pool_addresses(self.pool_name)
        self.instances = get_pool_instances(self.pool_name)

    def instance_addresses(self, instance_id: str) -> List[EIP]:
        return list(filter(lambda a: a.instance_id == instance_id, self.addresses))

    @property
    def available_addresses(self) -> List[EIP]:
        return list(filter(lambda a: not a.is_associated, self.addresses))

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
        self.refresh()
        instances = list(self.unattached_instances)
        if not instances:
            log.info(
                f'All instances in the EIP pool "{self.pool_name}" are associated with an EIP'
            )
            return

        allocation_ids = list(map(lambda a: a.allocation_id, self.available_addresses))
        if not allocation_ids:
            log.error(
                f'No more IP addresses in the pool "{self.pool_name}" to assign to the instances'
            )
            return

        if len(instances) > len(allocation_ids):
            log.warning(
                f'The Elastic IP pool "{self.pool_name}" is short of {len(instances) - len(allocation_ids)} addresses'
            )

        for instance_id, network_interface_id, allocation_id in [
            (instances[i].instance_id, instances[i].primary_network_interface_id, allocation_ids[i])
            for i in range(0, min(len(instances), len(allocation_ids)))
        ]:
            try:
                log.info(
                    f'associate ip address {allocation_id} from "{self.pool_name}" to network interface {network_interface_id} of instance {instance_id}'
                )
                ec2.associate_address(
                    NetworkInterfaceId=network_interface_id, AllocationId=allocation_id
                )
            except ClientError as e:
                log.error(
                    f'failed to associate ip address "{allocation_id}" from "{self.pool_name}" to network interface {network_interface_id} of instance "{instance_id}", {e}'
                )

    def remove_addresses(self, instance_id: str):
        """
        disassociate all the IP addresses of the pool from the instance `self.instance_id`
        """
        self.refresh()
        if not self.instance_addresses(instance_id):
            log.info(
                f'EIP from the pool {self.pool_name} no longer associated with instance "{instance_id}"'
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


def is_state_change_event(event):
    return event.get("source") == "aws.ec2" and event.get("detail-type") in [
        "EC2 Instance State-change Notification"
    ]


def is_add_address_event(event):
    return (
            is_state_change_event(event) and event.get("detail").get("state") == "running"
    )


def is_address_removed_event(event):
    return is_state_change_event(event) and event.get("detail").get("state") in [
        "stopping",
        "shutting-down",
        "terminated",
    ]


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


def put_cloudwatch_metric(pool_name: str):
    """
    Puts a customs metric indicating how many free EIPs remaining in a specific pool
    :param pool_name: the pool from which the EIP will be assigned
    """
    log.info("Putting remaining elastic ips metric")
    remaining_eips = len(list(filter(lambda eip: "AssociationId" not in eip, get_pool_addresses(pool_name))))
    log.info(f"Free elastic IPs remaining {remaining_eips}")
    response = cloudwatch.put_metric_data(
        MetricData=[
            {
                'MetricName': 'Available-EIPs',
                'Dimensions': [
                    {
                        'Name': 'EipPoolName',
                        'Value': pool_name
                    }
                ],
                'Unit': 'None',
                'Value': remaining_eips
            },
        ],
        Namespace='S24/FiZZ'
    )

    log.debug(response)


def handler(event: dict, context: dict):
    if is_add_address_event(event) or is_address_removed_event(event):
        instance = describe_pool_instance(event.get("detail").get("instance-id"))
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
        manager.add_addresses()

    elif is_timer(event):
        for pool_name in get_all_pool_names():
            manager = Manager(pool_name)
            manager.add_addresses()
            put_cloudwatch_metric(pool_name)

    elif is_state_change_event(event):
        log.debug("ignored state change event %s", event.get("detail", {}).get("state"))
    else:
        log.error(
            "ignoring event %s from source %s",
            event.get("detail-type"),
            event.get("source"),
        )
