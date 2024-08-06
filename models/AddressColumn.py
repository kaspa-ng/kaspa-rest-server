from sqlalchemy import TypeDecorator
from sqlalchemy.types import VARCHAR

from constants import ADDRESS_PREFIX


class AddressColumn(TypeDecorator):
    impl = VARCHAR
    cache_ok = True

    prefix = ADDRESS_PREFIX + ":"

    def process_bind_param(self, value, dialect):
        if value is not None:
            return value[len(self.prefix):]
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return self.prefix + value
        return value
