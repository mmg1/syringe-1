import ptypes
from ptypes import pstruct,parray,ptype,dyn,pstr,pbinary,utils
from ..__base__ import *

from .headers import virtualaddress
from . import headers

pbinary.setbyteorder(ptypes.config.byteorder.littleendian)

class TLS_Callbacks(parray.terminated):
    _object_ = uint32
    def isTerminator(self, value):
        return value.int() == 0

class IMAGE_TLS_DIRECTORY(pstruct.type):
    _fields_ = [
        (uint32, 'StartAddressOfRawData'),
        (uint32, 'EndAddressOfRawData'),
        (uint32, 'AddressOfIndex'),
        (virtualaddress(TLS_Callbacks, type=uint32), 'AddressOfCallbacks'),
        (uint32, 'SizeOfZeroFill'),
        (uint32, 'Characteristics'),
    ]

class IMAGE_TLS_DIRECTORY64(pstruct.type):
    _fields_ = [
        (uint64, 'StartAddressOfRawData'),
        (uint64, 'EndAddressOfRawData'),
        (uint64, 'AddressOfIndex'),
        (virtualaddress(TLS_Callbacks, type=uint64), 'AddressOfCallbacks'),
        (uint32, 'SizeOfZeroFill'),
        (uint32, 'Characteristics'),
    ]
