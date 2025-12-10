from collections import defaultdict

class DimensionConstructorSMT:
    def __init__(self, name, task, additional_information):
        self.name       = name
        self.task       = task
        self.encoder    = task.encoder
        self.addinfo    = additional_information
        self.var        = None
        self.var_domain = set()

        # generate the encodings
        self.formula = []
        self.__encode__(self.encoder)

    def __encode__(self, encoder):
        """!
        This function should return the encoding of the dimension.
        """
        raise NotImplementedError()
    
    def expr(self, model):
        """!
        This function should return the z3 expression of the dimension given the model.
        """
        raise NotImplementedError()


class DimensionConstructorSimulator:
    def __init__(self, task, name, addinfo):
        self.task = task
        self.name = name
        self.addinfo = addinfo