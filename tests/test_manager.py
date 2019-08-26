import copy
import boto3
from typing import List
from elastic_ip_manager import (
    handler,
    Manager,
    get_pool_instances,
    get_pool_addresses,
    get_all_pool_names,
)
from elastic_ip_manager.eip import EIP

event = {
    "id": "7bf73129-1428-4cd3-a780-95db273d1602",
    "detail-type": "EC2 Instance State-change Notification",
    "source": "aws.ec2",
    "account": "123456789012",
    "time": "2015-11-11T21:29:54Z",
    "region": "us-east-1",
    "resources": ["arn:aws:ec2:us-east-1:123456789012:instance/i-abcd1111"],
    "detail": {"instance-id": "i-abcd1111", "state": "running"},
}


ec2 = boto3.client("ec2")


def is_available_address(a):
    return "AssociationId" not in a


def is_unavailable_address(a):
    return "AssociationId" in a


def get_addresses() -> (List[EIP], List[EIP], List[EIP]):
    response = ec2.describe_addresses(
        Filters=[
            {"Name": "domain", "Values": ["vpc"]},
            {"Name": "tag:elastic-ip-manager-pool", "Values": ["bastion"]},
        ]
    )
    addresses = [EIP(a) for a in response["Addresses"]]
    assert len(addresses) == 2
    return (
        addresses,
        list(filter(is_available_address, addresses)),
        list(filter(is_unavailable_address, addresses)),
    )


def test_get_all_pool_names():
    pool_names = get_all_pool_names()
    assert pool_names == ["bastion"]


def test_get_addresses():
    addresses, _, _ = get_addresses()
    pool_addresses = get_pool_addresses("bastion")
    for a in get_pool_addresses("bastion"):
        assert a.pool_name == "bastion"
    assert set(addresses) == set(pool_addresses)


def test_get_pool_instances():
    instances = get_pool_instances("bastion")
    assert (
        len(instances) == 3
    ), "expected 3 ec2 instances with tag elastic-ip-manager-pool == bastion"


def return_all_ips_to_pool():
    for instance in get_pool_instances("bastion"):
        manager = Manager("bastion")
        manager.remove_addresses(instance.instance_id)

    _, available, _ = get_addresses()
    assert len(available) == 2


def test_remove_and_add():
    return_all_ips_to_pool()

    instances = get_pool_instances("bastion")
    for instance in instances:
        event["detail"]["state"] = "running"
        event["detail"]["instance-id"] = instance.instance_id
        handler(event, {})

    _, available, allocated = get_addresses()
    assert len(available) == 0

    event["detail"]["state"] = "terminated"
    event["detail"]["instance-id"] = instances[0].instance_id
    handler(event, {})

    _, available, _ = get_addresses()
    assert len(available) == 0


def test_remove_non_existing_instance():
    event["detail"]["state"] = "terminated"
    event["detail"]["instance-id"] = " i-000000000000a4a41"
    handler(event, {})


def test_add_non_existing_instance_eip():
    return_all_ips_to_pool()
    event["detail"]["state"] = "running"
    event["detail"]["instance-id"] = "i-000000000000a4a41"
    handler(event, {})


def test_timer():
    get_addresses()
    return_all_ips_to_pool()

    event = {"detail-type": "Scheduled Event", "source": "aws.events", "detail": {}}
    handler(event, {})

    _, available, _ = get_addresses()
    assert len(available) == 0

    event = {"detail-type": "Scheduled Event", "source": "aws.events", "detail": {}}
    handler(event, {})

    _, available, _ = get_addresses()
    assert len(available) == 0


def test_invalid_event():
    get_addresses()
    return_all_ips_to_pool()

    event2 = copy.deepcopy(event)
    event2["source"] = "aws.unknown"
    handler(event2, {})

    _, available, _ = get_addresses()
    assert len(available) == 2
