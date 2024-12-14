from collections import defaultdict

class DimensionConstructorSMT:
    def __init__(self, name, encoder, additional_information):
        self.name = name
        self.additional_information = additional_information
        self.var  = None
        self.encoder_function = defaultdict(dict)
        self.var_domain = set()
        self.encodings = []
        self.logs = []

        self.__encode__(encoder)
    
    def __len__(self):
        return len(self.var_domain)

    def __encode__(self, encoder):
        """!
        This function should return the encoding of the dimension.
        """
        raise NotImplementedError

    def discretize(self, value):
        """!
        This function should return the discretized value of the dimension.
        """
        raise NotImplementedError

    def value(self, object):
        """!
        This function should return the value of the dimension for the given object.
        """
        raise NotImplementedError
    
    def behaviour_expression(self, plan):
        return self.var == self.discretize(self.value(plan))