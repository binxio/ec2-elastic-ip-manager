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

from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

ec2 = boto3.client("ec2")
autoscaling = boto3.client("autoscaling")


class Manager(object):
    def __init__(self, auto_scaling_group: dict, pool_name: str):

        self.pool_name: str = pool_name
        self.auto_scaling_group: dict = auto_scaling_group
        self.auto_scaling_group_name: str = auto_scaling_group["AutoScalingGroupName"]

        self.addresses: List[dict] = []
        self.get_addresses()

    def get_addresses(self):
        response = ec2.describe_addresses(
            Filters=[
                {"Name": "domain", "Values": ["vpc"]},
                {"Name": "tag:asg-elastic-ip-manager-pool", "Values": [self.pool_name]},
            ]
        )
        self.addresses = response["Addresses"]

    def instance_addresses(self, instance_id: str) -> List[dict]:
        return list(
            filter(lambda a: a.get("InstanceId") == instance_id, self.addresses)
        )

    @property
    def available_addresses(self) -> List[dict]:
        return list(filter(lambda a: "InstanceId" not in a, self.addresses))

    @property
    def instances(self) -> Set[str]:
        """
        all healthy InServices instances of the `self.auto_scaling_group`
        """
        return set(
            map(
                lambda i: i["InstanceId"],
                filter(
                    lambda i: i["LifecycleState"] == "InService"
                    and i["HealthStatus"] == "Healthy",
                    self.auto_scaling_group["Instances"],
                ),
            )
        )

    @property
    def attached_instances(self) -> Set[str]:
        """
        all instances attached to an EIP in `self.addresses`
        """
        return set(
            map(
                lambda a: a["InstanceId"],
                filter(lambda a: "InstanceId" in a, self.addresses),
            )
        )

    @property
    def unattached_instances(self) -> Set[str]:
        """
        all instances in the `self.auto_scaling_group` which do not have an IP address assigned from `self.addresses`
        """
        return self.instances - self.attached_instances

    def add_addresses(self):
        """
        ensure an ip address is associated with all healthy inservice asg instances.
        """
        instances = list(self.unattached_instances)
        if not instances:
            log.info(
                f'All healthy in-service instances in the auto scaling group "{self.auto_scaling_group_name}" are associated with an EIP'
            )
            return

        allocation_ids = list(
            map(lambda a: a["AllocationId"], self.available_addresses)
        )
        if len(instances) > len(allocation_ids):
            log.warning(
                f'The Elastic IP pool {self.pool_name} is short of {len(instances) - len(allocation_ids)} addresses to assign to the auto scaling group "{self.auto_scaling_group_name}"'
            )

        if not allocation_ids:
            log.error(
                f'No more IP addresses in the pool {self.pool_name} to assign to the auto scaling group "{self.auto_scaling_group_name}"'
            )
            return

        for instance_id, allocation_id in [
            (instances[i], allocation_id)
            for i, allocation_id in enumerate(allocation_ids)
        ]:
            try:
                log.info(
                    f"associate ip address {allocation_id} from {self.pool_name} to instance {instance_id}"
                )
                ec2.associate_address(
                    InstanceId=instance_id, AllocationId=allocation_id
                )
            except ClientError as e:
                log.error(
                    f"failed to add ip address {allocation_id} from {self.pool_name} to instance {instance_id}, {e}"
                )

    def remove_addresses(self, instance_id: str):
        """
        disassociate all the IP addresses of the pool from the instance `self.instance_id`
        :return:
        """
        if not self.instance_addresses(instance_id):
            log.info(
                f"instance {instance_id} of auto scaling group {self.auto_scaling_group_name} terminated, but did not have an EIP associated"
            )
            return

        for allocation_id, association_id in map(
            lambda a: (a["AllocationId"], a["AssociationId"]),
            self.instance_addresses(instance_id),
        ):
            try:
                log.info(
                    f"returning ip address {allocation_id} from instance {instance_id} to pool {self.pool_name}"
                )
                ec2.disassociate_address(AssociationId=association_id)
            except ClientError as e:
                log.error(
                    f"failed to remove elastic ip address {allocation_id} from instance {instance_id}, {e}"
                )


def is_add_address_event(event):
    return event.get("source") == "aws.autoscaling" and event.get("detail-type") in [
        "EC2 Instance Launch Successful"
    ]


def is_remove_address_event(event) -> bool:
    return event.get("source") == "aws.autoscaling" and event.get("detail-type") in [
        "EC2 Instance Terminate Successful",
        "EC2 Instance Launch Unsuccessful",
    ]


def is_timer(event) -> bool:
    return event.get("source") == "aws.events" and event.get("detail-type") in [
        "Scheduled Event"
    ]


def get_pool_name(auto_scaling_group: Optional[dict]) -> str:

    result = None
    if auto_scaling_group:
        result = next(
            map(
                lambda t: t["Value"],
                filter(
                    lambda t: t["Key"] == "asg-elastic-ip-manager-pool",
                    auto_scaling_group.get("Tags", []),
                ),
            ),
            None,
        )
    if not result:
        log.debug(
            'ignoring auto scaling group "%s" as it is not associated with an EIP Pool',
            auto_scaling_group["AutoScalingGroupName"],
        )
    return result


def get_auto_scaling_group_by_event(event: dict) -> Optional[dict]:
    if event.get("source") == "aws.autoscaling":
        try:
            response = autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[
                    event.get("detail", {}).get("AutoScalingGroupName")
                ]
            )
            if response["AutoScalingGroups"]:
                return response["AutoScalingGroups"][0]

            log.error(
                "no auto scaling group found by name on event %s", event
            )
        except ClientError as e:
            log.error(
                "failed to get auto scaling group by name on event %s, %s", event, e
            )
    return None


def get_all_auto_scaling_groups() -> List[dict]:
    result = []
    paginator = autoscaling.get_paginator("describe_auto_scaling_groups")
    for response in paginator.paginate():
        result.extend(list(filter(get_pool_name, response["AutoScalingGroups"])))
    return result


def handler(event: dict, context: dict):
    if is_add_address_event(event) or is_remove_address_event(event):
        auto_scaling_group = get_auto_scaling_group_by_event(event)
        if not auto_scaling_group:
            return

        pool_name = get_pool_name(auto_scaling_group)
        if pool_name:
            manager = Manager(auto_scaling_group, pool_name)
            if is_add_address_event(event):
                manager.add_addresses()
            elif is_remove_address_event(event):
                manager.remove_addresses(event["detail"]["EC2InstanceId"])

    elif is_timer(event):
        for auto_scaling_group in get_all_auto_scaling_groups():
            manager = Manager(auto_scaling_group, get_pool_name(auto_scaling_group))
            manager.add_addresses()
    else:
        log.error(
            "ignoring event %s from source %s",
            event.get("detail-type"),
            event.get("source"),
        )
