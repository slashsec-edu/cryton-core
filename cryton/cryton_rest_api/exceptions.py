from rest_framework.exceptions import APIException


class ApiObjectDoesNotExist(APIException):
    status_code = 404
    default_detail = 'Object does not exist'
    default_code = 'object_not_found'


class ApiWrongOrMissingArgument(APIException):
    def __init__(self, param_name, param_type, name="This field is required."):
        default_detail = {"name": name,
                          "param_name": param_name,
                          "param_type": param_type}
        super().__init__(default_detail)

    status_code = 400
    default_code = 'object_not_found'


class ApiWrongFormat(APIException):
    status_code = 400
    default_detail = 'Wrong input format'
    default_code = 'wrong_input'


class ApiInternalError(APIException):
    status_code = 500
    default_detail = 'Something went wrong'
    default_code = 'internal_error'


class ApiWrongObjectState(APIException):
    status_code = 400
    default_detail = 'Object is not in the correct state'
    default_code = 'wrong_state'


class ApiWrongObject(APIException):
    status_code = 400
    default_detail = 'Object is wrong'
    default_code = 'wrong_object'
