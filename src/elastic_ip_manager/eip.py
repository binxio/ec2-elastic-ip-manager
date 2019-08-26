from typing import Optional

class EIP(dict):
    def __init__(self, instance: dict):
        self.update(instance)

    @property
    def allocation_id(self) -> str:
        return self.get("AllocationId")

    @property
    def association_id(self) -> Optional[str]:
        return self.get("AssociationId")

    @property
    def is_available(self) -> bool:
        return self.association_id is not None

    @property
    def instance_id(self) -> Optional[str]:
        return self.get("InstanceId")

    @property
    def pool_name(self) -> Optional[str]:
        return self.tags.get("elastic-ip-manager-pool")

    @property
    def tags(self) -> dict:
        return {t["Key"]: t["Value"] for t in self["Tags"]}

    def __key(self):
        return self['AllocationId']

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, other):
        return self.__key() == other.__key()

    def __str__(self):
        return str(self.__key())
