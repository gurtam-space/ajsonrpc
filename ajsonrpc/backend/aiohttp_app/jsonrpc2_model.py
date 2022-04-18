from .utils import get_result_item


# base model for jsonrpc2
class BaseJSONRPC20Model:
    """
    :param list fields: list return fields
    """
    def __init__(self, fields: list = None):
        self._getting_fields = fields
        all_fields = self.allowed_fields()
        self.fields = [el for el in fields if el in all_fields] if fields else list(all_fields)
        if not self.fields:
            raise ValueError('fields is empty')

    @classmethod
    # list allowed fields
    def allowed_fields(cls) -> tuple:
        return ()

    @classmethod
    # fields schema, example: { id: fleet_cid } = if get field 'id' then return field 'fleet_cid'
    def fields_dict(cls) -> dict:
        return {}

    def get_result_item(self, item: dict, f_dict: dict = None, filter_isset: bool = False) -> dict:
        if not item:
            return {}
        fields_dict = self.fields_dict()
        if f_dict:
            fields_dict.update(f_dict)
        return get_result_item(item, self.fields, fields_dict, filter_isset=filter_isset)
