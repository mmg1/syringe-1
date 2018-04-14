import ptypes, osi.__base__
from ptypes import ptype
class layer(ptype.definition):
    cache = {}

class stackable(osi.__base__.stackable):
    def nextlayer_id(self):
        raise NotImplementedError

    def nextlayer(self):
        id = self.nextlayer_id()
        res = layer.lookup(id, dyn.clone(layer.default, type=id))
        return (res, None)
