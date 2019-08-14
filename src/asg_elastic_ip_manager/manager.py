"""
AWS Auto Scaling Elastic IP manager

Manages the ip addresses associated to an autoscaling group instance. 

When a lifecycle terminating event occurs, the manager will remove all the elastic ip addresses that are associated
with the instance.

When a lifecycle launching event completed successfully, the manager will add a elastic ip address with the instance. If
no elastic ips are available, it will cancel the launch event.
"""
import os
import boto3
import logging
from typing import List, Set

from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

ec2 = boto3.client("ec2")
autoscaling = boto3.client("autoscaling")


class Manager(object):
    def __init__(self, event: dict):
        self.event: dict = event

        self.pool_name: str = ''
        self.auto_scaling_group: dict = {}

        self.get_auto_scaling_group()

        self.addresses: List[dict] = []
        self.get_addresses()

    def get_addresses(self):
        response = ec2.describe_addresses(
            Filters=[
                {"Name": "domain", "Values": ["vpc"]},
                {"Name": "tag:EIPPoolName", "Values": [self.pool_name]},
            ]
        )
        self.addresses = response["Addresses"]

    def get_auto_scaling_group(self):
        response = autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[self.auto_scaling_group_name]
        )
        self.auto_scaling_group = response["AutoScalingGroups"][0]
        self.pool_name = next(
            map(
                lambda t: t["Value"],
                filter(
                    lambda t: t["Key"] == "EIPPoolName", self.auto_scaling_group["Tags"]
                ),
            ),
            None,
        )

    @property
    def instance_id(self):
        return self.event["detail"]["EC2InstanceId"]

    @property
    def instance_addresses(self) -> List[dict]:
        return list(
            filter(
                lambda a: "InstanceId" in a and a["InstanceId"] == self.instance_id,
                self.addresses,
            )
        )

    @property
    def available_addresses(self) -> List[dict]:
        return list(filter(lambda a: "InstanceId" not in a, self.addresses))

    @property
    def is_remove_address_event(self) -> bool:
        return self.event.get("detail-type") in [
            "EC2 Instance Terminate Successful",
            "EC2 Instance Launch Unsuccessful",
        ]

    @property
    def is_add_address_event(self):
        return self.event.get("detail-type") in [
            "EC2 Instance Terminate Unsuccessful",
            "EC2 Instance Launch Successful",
        ]

    @property
    def auto_scaling_group_name(self):
        return self.event["detail"]["AutoScalingGroupName"]

    @property
    def instances(self) -> Set[str]:
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
        return set(
            map(
                lambda a: a["InstanceId"],
                filter(lambda a: "InstanceId" in a, self.addresses),
            )
        )

    @property
    def unattached_instances(self) -> Set[str]:
        return self.instances - self.attached_instances

    def add_addresses(self):
        """
        ensure an ip address with all healthy associated with all healthy inservice asg instances.
        """

        instances = list(self.unattached_instances)
        if not instances:
            log.info(
                f'All healthy in-service instances in the autoscaling group "{self.auto_scaling_group_name}" are associated with an EIP'
            )
            return

        allocation_ids = list(
            map(lambda a: a["AllocationId"], self.available_addresses)
        )
        if len(instances) > len(allocation_ids):
            log.warning(
                f'The Elastic IP pool {self.pool_name} is short of {len(instances) - len(allocation_ids)} addresses to assign to the autoscaling group "{self.auto_scaling_group_name}"'
            )

        if not allocation_ids:
            log.error(
                f'No more IP addresses in the pool {self.pool_name} to assign to the autoscaling group "{self.auto_scaling_group_name}"'
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

    def remove_addresses(self):
        if not self.instance_addresses:
            log.info(f"instance {self.instance_id} of auto scaling group {self.auto_scaling_group_name} terminated, but did not have an EIP associated")
            return
        
        for allocation_id, association_id in map(
            lambda a: (a["AllocationId"], a["AssociationId"]), self.instance_addresses
        ):
            try:
                log.info(
                    f"returned ip address {allocation_id} from instance {self.instance_id} to pool {self.pool_name}"
                )
                ec2.disassociate_address(AssociationId=association_id)
            except ClientError as e:
                log.error("failed to remove elastic ip address, %s", e)

    def handle(self):
        if not self.pool_name:
            log.info(
                f'ignoring autoscaling group "{self.auto_scaling_group_name}" is not associated with an EIP Pool'
            )
            return

        if self.is_add_address_event:
            self.add_addresses()
        elif self.is_remove_address_event:
            self.remove_addresses()
        else:
            log.debug("ignoring event %s", self.event["event-type"])


def handler(event, context):
    if "source" in event and event["source"] == "aws.autoscaling":
        manager = Manager(event)
        manager.handle()
    else:
        log.error("unknown event received, %s", event)
