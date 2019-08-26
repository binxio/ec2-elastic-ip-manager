class EC2Instance(dict):
    def  __init__(self, instance: dict):
        self.update(instance)

    @property
    def instance_id(self) -> str:
        return self["InstanceId"]

    @property
    def pool_name(self) -> str:
        return self.tags.get("elastic-ip-manager-pool", None)

    @property
    def tags(self) -> dict:
        return {t["Key"]: t["Value"] for t in self["Tags"]}

    def __key(self):
        return self['InstanceId']

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, other):
        return self.__key() == other.__key()

    def __str__(self):
        return str(self.__key())
